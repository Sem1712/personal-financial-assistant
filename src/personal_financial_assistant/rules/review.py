"""Explicit review of protected AI change suggestions."""

from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import (
    ApplicationApproval,
    ApplicationConflict,
    ChangeSuggestion,
    ClassificationPreference,
    Merchant,
    MerchantDefault,
    MerchantMatch,
)
from personal_financial_assistant.transactions import lock_occurrence

from .application import prepare_application
from .proposals import (
    ChangeSuggestionRecord,
    RuleChangeInput,
    RuleRow,
    apply_change_to_row,
    get_rule_in_session,
    validate_change_in_session,
)
from .storage import RulesStorageError, rules_transaction
from .types import (
    EntryKind,
    EvaluationResult,
    MatchingEntryInput,
    MatchKind,
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
    RuleNotFound,
    RuleReference,
    RuleValidationError,
    validate_id,
)

type Database = AsyncEngine | AsyncConnection


class StaleReview(Exception):
    """The reviewed inputs changed; obtain a fresh preview before deciding."""


@dataclass(frozen=True)
class ChangePreview:
    suggestion_id: int
    snapshot_id: str
    target_kind: str
    target_id: int
    action: str
    current: dict[str, object] = field(repr=False)
    proposed: dict[str, object] = field(repr=False)
    affected_confirmed: tuple[RuleReference, ...]
    reviewed: dict[str, object] = field(repr=False)


@dataclass(frozen=True)
class ApplicationConflictRecord:
    id: int
    occurrence_id: int
    ai_entry: RuleReference
    confirmed_entry: RuleReference
    state: str


@dataclass(frozen=True)
class ApplicationPreview:
    conflict: ApplicationConflictRecord
    snapshot_id: str
    result: EvaluationResult = field(repr=False)
    reviewed: dict[str, object] = field(repr=False)


def review_snapshot_is_current(reviewed: object, current: object) -> bool:
    """Compare the complete reviewed state, not just the target revision."""
    return reviewed == current


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise RuleValidationError("Invalid suggestion payload")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise RuleValidationError("Invalid suggestion payload")
    return value


def _suggested_rule_change(suggestion: ChangeSuggestion) -> RuleChangeInput:
    if suggestion.action == "disable":
        if suggestion.payload:
            raise RuleValidationError("Invalid suggestion payload")
        return None
    payload = suggestion.payload
    try:
        if suggestion.target_kind == EntryKind.MATCHING_ENTRY.value:
            return MatchingEntryInput(
                _integer(payload, "merchant_id"),
                MatchKind(_text(payload, "kind")),
                _text(payload, "text"),
            )
        if suggestion.target_kind == EntryKind.MERCHANT_DEFAULT.value:
            return MerchantDefaultInput(
                _integer(payload, "merchant_id"), _text(payload, "category")
            )
        if suggestion.target_kind == EntryKind.CLASSIFICATION_PREFERENCE.value:
            kind = PreferenceKind(_text(payload, "kind"))
            merchant_id = payload.get("merchant_id")
            match_text = payload.get("match_text")
            if merchant_id is not None and type(merchant_id) is not int:
                raise RuleValidationError("Invalid suggestion payload")
            if match_text is not None and not isinstance(match_text, str):
                raise RuleValidationError("Invalid suggestion payload")
            return PreferenceInput(
                kind, _text(payload, "category"), merchant_id, match_text
            )
    except ValueError:
        raise RuleValidationError("Invalid suggestion payload") from None
    raise RuleValidationError("Invalid suggestion target")


def _target_reference(suggestion: ChangeSuggestion) -> RuleReference:
    try:
        kind = EntryKind(suggestion.target_kind)
    except ValueError:
        raise RuleValidationError("Invalid suggestion target") from None
    if kind is EntryKind.MATCHING_ENTRY:
        target_id = suggestion.target_match_id
    elif kind is EntryKind.MERCHANT_DEFAULT:
        target_id = suggestion.target_default_id
    else:
        target_id = suggestion.target_preference_id
    if target_id is None:
        raise RulesStorageError("Suggestion target is missing")
    return RuleReference(kind, target_id)


async def _suggestion(session: AsyncSession, suggestion_id: int) -> ChangeSuggestion:
    validate_id(suggestion_id)
    row = await session.get(ChangeSuggestion, suggestion_id)
    if row is None:
        raise RuleNotFound("Suggestion not found")
    if row.state not in ("pending", "stale"):
        raise RuleValidationError("Suggestion is already decided")
    return row


async def _affected_confirmed(
    session: AsyncSession, merchant_id: int
) -> tuple[tuple[RuleReference, int], ...]:
    result: list[tuple[RuleReference, int]] = []
    for kind, model in (
        (EntryKind.MATCHING_ENTRY, MerchantMatch),
        (EntryKind.MERCHANT_DEFAULT, MerchantDefault),
        (EntryKind.CLASSIFICATION_PREFERENCE, ClassificationPreference),
    ):
        rows = (
            await session.execute(
                select(model.id, model.revision).where(
                    model.merchant_id == merchant_id, model.confirmed.is_(True)
                )
            )
        ).all()
        result.extend((RuleReference(kind, row.id), row.revision) for row in rows)
    return tuple(sorted(result, key=lambda item: (item[0].kind.value, item[0].id)))


async def _change_state(
    session: AsyncSession, suggestion: ChangeSuggestion
) -> tuple[
    dict[str, object],
    tuple[RuleReference, ...],
    Merchant | RuleRow,
    RuleChangeInput | MerchantInput,
    dict[str, object],
]:
    target: Merchant | RuleRow
    data: RuleChangeInput | MerchantInput
    affected: tuple[tuple[RuleReference, int], ...]
    if suggestion.target_kind == "merchant":
        if suggestion.target_merchant_id is None:
            raise RulesStorageError("Suggestion target is missing")
        merchant = await session.get(Merchant, suggestion.target_merchant_id)
        if merchant is None:
            raise RuleNotFound("Merchant not found")
        target = merchant
        data = (
            None
            if suggestion.action == "disable"
            else MerchantInput(_text(suggestion.payload, "canonical_name"))
        )
        affected = await _affected_confirmed(session, merchant.id)
        target_id = merchant.id
        target_state: dict[str, object] = {
            "revision": merchant.revision,
            "enabled": merchant.enabled,
            "enabled_revision": merchant.enabled_revision,
            "canonical_name": merchant.canonical_name,
        }
    else:
        reference = _target_reference(suggestion)
        target = await get_rule_in_session(session, reference)
        data, _ = await validate_change_in_session(
            session, target, _suggested_rule_change(suggestion)
        )
        affected = ((reference, target.revision),) if target.confirmed else ()
        target_id = reference.id
        target_state = {
            "revision": target.revision,
            "enabled": target.enabled,
            "confirmed": target.confirmed,
            "origin": target.origin,
            "merchant_id": target.merchant_id,
        }
        if isinstance(target, MerchantMatch):
            target_state.update({"kind": target.kind, "text": target.original_text})
        elif isinstance(target, MerchantDefault):
            target_state["category"] = target.category
        else:
            target_state.update(
                {
                    "kind": target.match_kind,
                    "match_text": target.match_text,
                    "category": target.category,
                }
            )
        merchant_ids = {
            merchant_id
            for merchant_id in (
                target.merchant_id,
                data.merchant_id if data is not None else None,
            )
            if merchant_id is not None
        }
        merchants = (
            await session.execute(
                select(Merchant.id, Merchant.enabled, Merchant.enabled_revision).where(
                    Merchant.id.in_(merchant_ids)
                )
            )
        ).all()
        if len(merchants) != len(merchant_ids):
            raise RuleNotFound("Merchant not found")
        target_state["merchants"] = [
            {
                "id": row.id,
                "enabled": row.enabled,
                "enabled_revision": row.enabled_revision,
            }
            for row in sorted(merchants, key=lambda row: row.id)
        ]
    snapshot: dict[str, object] = {
        "target_kind": suggestion.target_kind,
        "target_id": target_id,
        "target": target_state,
        "action": suggestion.action,
        "payload": suggestion.payload,
        "affected": [
            {"kind": ref.kind.value, "id": ref.id, "revision": revision}
            for ref, revision in affected
        ],
    }
    return snapshot, tuple(ref for ref, _ in affected), target, data, target_state


async def preview_change_suggestion(
    bind: Database, suggestion_id: int
) -> ChangePreview:
    """Store the exact target and affected confirmations being presented."""
    async with rules_transaction(bind) as session:
        suggestion = await _suggestion(session, suggestion_id)
        snapshot, affected, _, _, target_state = await _change_state(
            session, suggestion
        )
        snapshot_id = str(uuid4())
        suggestion.review_snapshot = {"id": snapshot_id, "state": snapshot}
        target_id = snapshot["target_id"]
        if type(target_id) is not int:
            raise RulesStorageError("Suggestion target is invalid")
        return ChangePreview(
            suggestion.id,
            snapshot_id,
            suggestion.target_kind,
            target_id,
            suggestion.action,
            target_state,
            suggestion.payload,
            affected,
            snapshot,
        )


async def _decide_change(
    bind: Database, suggestion_id: int, snapshot_id: str, *, approve: bool
) -> None:
    stale = False
    async with rules_transaction(bind) as session:
        suggestion = await _suggestion(session, suggestion_id)
        snapshot = suggestion.review_snapshot
        if not snapshot_id:
            raise RuleValidationError("Invalid review snapshot ID")
        try:
            current, _, target, data, _ = await _change_state(session, suggestion)
        except RuleNotFound, RuleValidationError:
            stale = True
        else:
            stale = (
                snapshot is None
                or snapshot.get("id") != snapshot_id
                or not review_snapshot_is_current(snapshot.get("state"), current)
            )
            if not stale:
                if approve:
                    if isinstance(target, Merchant):
                        if data is None and target.enabled:
                            target.enabled = False
                            target.enabled_revision += 1
                            target.revision += 1
                        elif (
                            isinstance(data, MerchantInput)
                            and target.canonical_name != data.canonical_name
                        ):
                            target.canonical_name = data.canonical_name
                            target.revision += 1
                    elif not isinstance(data, MerchantInput):
                        apply_change_to_row(target, data, ProposalOrigin.AI)
                    else:
                        raise RulesStorageError("Suggestion target is invalid")
                suggestion.state = "approved" if approve else "rejected"
        if stale:
            suggestion.state = "stale"
            suggestion.review_snapshot = None
    if stale:
        raise StaleReview("Review is stale; obtain a new preview")


async def approve_change_suggestion(
    bind: Database, suggestion_id: int, snapshot_id: str
) -> None:
    """Approve only the exact preview, atomically applying the reviewed change."""
    await _decide_change(bind, suggestion_id, snapshot_id, approve=True)


async def reject_change_suggestion(
    bind: Database, suggestion_id: int, snapshot_id: str
) -> None:
    """Reject the exact preview without changing the protected target."""
    await _decide_change(bind, suggestion_id, snapshot_id, approve=False)


def _change_record(row: ChangeSuggestion) -> ChangeSuggestionRecord:
    if row.target_kind == "merchant":
        target_id = row.target_merchant_id
    else:
        target_id = _target_reference(row).id
    if target_id is None:
        raise RulesStorageError("Suggestion target is missing")
    return ChangeSuggestionRecord(
        row.id,
        row.target_kind,
        target_id,
        row.target_revision,
        row.action,
        row.origin,
        row.state,
    )


async def inspect_change_suggestion(
    bind: Database, suggestion_id: int
) -> ChangeSuggestionRecord:
    """Inspect any suggestion, including decided suggestions."""
    validate_id(suggestion_id)
    async with rules_transaction(bind) as session:
        row = await session.get(ChangeSuggestion, suggestion_id)
        if row is None:
            raise RuleNotFound("Suggestion not found")
        return _change_record(row)


async def list_change_suggestions(bind: Database) -> tuple[ChangeSuggestionRecord, ...]:
    """List suggestions that require review."""
    async with rules_transaction(bind) as session:
        rows = (
            await session.scalars(
                select(ChangeSuggestion)
                .where(ChangeSuggestion.state.in_(("pending", "stale")))
                .order_by(ChangeSuggestion.id)
            )
        ).all()
        return tuple(_change_record(row) for row in rows)


def _conflict_reference(row: ApplicationConflict, *, ai: bool) -> RuleReference:
    try:
        kind = EntryKind(row.ai_kind if ai else row.confirmed_kind)
    except ValueError:
        raise RulesStorageError("Conflict reference is invalid") from None
    if kind is EntryKind.MATCHING_ENTRY:
        entry_id = row.ai_match_id if ai else row.confirmed_match_id
    elif kind is EntryKind.MERCHANT_DEFAULT:
        entry_id = row.ai_default_id if ai else row.confirmed_default_id
    else:
        entry_id = row.ai_preference_id if ai else row.confirmed_preference_id
    if entry_id is None:
        raise RulesStorageError("Conflict reference is missing")
    return RuleReference(kind, entry_id)


def _conflict_record(row: ApplicationConflict) -> ApplicationConflictRecord:
    return ApplicationConflictRecord(
        row.id,
        row.occurrence_id,
        _conflict_reference(row, ai=True),
        _conflict_reference(row, ai=False),
        row.state,
    )


async def _locked_conflict(
    session: AsyncSession, conflict_id: int
) -> ApplicationConflict:
    validate_id(conflict_id)
    row = await session.get(ApplicationConflict, conflict_id)
    if row is None:
        raise RuleNotFound("Application conflict not found")
    await lock_occurrence(session, row.occurrence_id)
    return row


async def inspect_application_conflict(
    bind: Database, conflict_id: int
) -> ApplicationConflictRecord:
    """Inspect a typed per-occurrence conflict."""
    async with rules_transaction(bind) as session:
        return _conflict_record(await _locked_conflict(session, conflict_id))


async def list_application_conflicts(
    bind: Database,
) -> tuple[ApplicationConflictRecord, ...]:
    """List application conflicts awaiting a user decision."""
    async with rules_transaction(bind) as session:
        rows = (
            await session.scalars(
                select(ApplicationConflict)
                .where(ApplicationConflict.state.in_(("pending", "stale")))
                .order_by(ApplicationConflict.id)
            )
        ).all()
        return tuple(_conflict_record(row) for row in rows)


async def preview_application_conflict(
    bind: Database, conflict_id: int
) -> ApplicationPreview:
    """Show the actual outcome if this single conflict were approved."""
    result: ApplicationPreview | None = None
    async with rules_transaction(bind) as session:
        row = await _locked_conflict(session, conflict_id)
        if row.state not in ("pending", "stale", "rejected"):
            raise RuleValidationError("Application conflict is already approved")
        prepared = await prepare_application(
            session, row.occurrence_id, hypothetical_approval=row.id
        )
        if row.id not in prepared.scopes:
            row.state = "stale"
            row.review_snapshot = None
        else:
            snapshot_id = str(uuid4())
            row.review_snapshot = {"id": snapshot_id, "state": prepared.snapshot}
            result = ApplicationPreview(
                _conflict_record(row), snapshot_id, prepared.result, prepared.snapshot
            )
    if result is None:
        raise StaleReview("Conflict no longer applies")
    return result


async def _decide_application(
    bind: Database, conflict_id: int, snapshot_id: str, *, approve: bool
) -> None:
    if not snapshot_id:
        raise RuleValidationError("Invalid review snapshot ID")
    stale = False
    async with rules_transaction(bind) as session:
        row = await _locked_conflict(session, conflict_id)
        if row.state not in ("pending", "stale", "rejected"):
            raise RuleValidationError("Application conflict is already approved")
        snapshot = row.review_snapshot
        prepared = await prepare_application(
            session, row.occurrence_id, hypothetical_approval=row.id
        )
        scope = prepared.scopes.get(row.id)
        if (
            scope is None
            or snapshot is None
            or snapshot.get("id") != snapshot_id
            or not review_snapshot_is_current(snapshot.get("state"), prepared.snapshot)
        ):
            row.state = "stale"
            row.review_snapshot = None
            stale = True
        elif approve:
            approval = await session.get(ApplicationApproval, row.id)
            if approval is None:
                approval = ApplicationApproval(conflict_id=row.id)
                session.add(approval)
            approval.ai_revision = scope.ai_revision
            approval.confirmed_revision = scope.confirmed_revision
            approval.evidence_revision = scope.evidence_revision
            approval.merchant_revisions = [
                list(pair) for pair in scope.merchant_revisions
            ]
            row.state = "approved"
            row.review_snapshot = None
        else:
            row.state = "rejected"
            row.review_snapshot = None
    if stale:
        raise StaleReview("Review is stale; obtain a new preview")


async def approve_application_conflict(
    bind: Database, conflict_id: int, snapshot_id: str
) -> None:
    """Approve one typed pair at the exact reviewed occurrence and revisions."""
    await _decide_application(bind, conflict_id, snapshot_id, approve=True)


async def reject_application_conflict(
    bind: Database, conflict_id: int, snapshot_id: str
) -> None:
    """Reject one reviewed application without changing either rule."""
    await _decide_application(bind, conflict_id, snapshot_id, approve=False)
