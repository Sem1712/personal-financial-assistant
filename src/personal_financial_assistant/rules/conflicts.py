"""Per-occurrence AI application conflicts and scoped approval checks."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from personal_financial_assistant.infrastructure.models import (
    ApplicationApproval,
    ApplicationConflict,
    Merchant,
)

from .storage import RulesStorageError
from .types import (
    BlockedAIConflict,
    EntryKind,
    ProposalOrigin,
    RuleReference,
    RuleValidationError,
    validate_id,
)

type OutcomeKind = Literal["merchant", "category"]


@dataclass(frozen=True)
class ConflictCandidate:
    reference: RuleReference
    revision: int
    origin: ProposalOrigin
    confirmed: bool
    outcome: str | int = field(repr=False)
    merchant_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ApprovalScope:
    ai_entry: RuleReference
    ai_revision: int
    confirmed_entry: RuleReference
    confirmed_revision: int
    evidence_revision: int
    merchant_revisions: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ConflictPair:
    conflict_id: int
    scope: ApprovalScope
    state: str
    approved: bool


@dataclass(frozen=True)
class ConflictResolution:
    eligible: tuple[ConflictCandidate, ...]
    blocked: tuple[BlockedAIConflict, ...]
    pairs: tuple[ConflictPair, ...]


def application_is_approved(
    state: str, approved: ApprovalScope | None, current: ApprovalScope
) -> bool:
    """An approval removes only one block at its reviewed revisions."""
    return state == "approved" and approved == current


async def _merchant_revisions(
    session: AsyncSession, first: ConflictCandidate, second: ConflictCandidate
) -> tuple[tuple[int, int], ...]:
    ids = set(first.merchant_ids + second.merchant_ids)
    if not ids:
        return ()
    rows = (
        await session.execute(
            select(Merchant.id, Merchant.enabled_revision).where(Merchant.id.in_(ids))
        )
    ).all()
    if len(rows) != len(ids):
        raise RulesStorageError("Referenced merchant is unavailable")
    return tuple(sorted((row.id, row.enabled_revision) for row in rows))


def _stored_scope(
    approval: ApplicationApproval, ai: RuleReference, confirmed: RuleReference
) -> ApprovalScope:
    revisions: list[tuple[int, int]] = []
    for pair in approval.merchant_revisions:
        if (
            len(pair) != 2
            or type(pair[0]) is not int
            or type(pair[1]) is not int
            or pair[0] <= 0
            or pair[1] <= 0
        ):
            raise RulesStorageError("Stored approval scope is invalid")
        revisions.append((pair[0], pair[1]))
    if len({merchant_id for merchant_id, _ in revisions}) != len(revisions):
        raise RulesStorageError("Stored approval scope is invalid")
    return ApprovalScope(
        ai,
        approval.ai_revision,
        confirmed,
        approval.confirmed_revision,
        approval.evidence_revision,
        tuple(sorted(revisions)),
    )


def _reference_column(reference: RuleReference, *, ai: bool) -> ColumnElement[bool]:
    if ai:
        if reference.kind is EntryKind.MATCHING_ENTRY:
            return ApplicationConflict.ai_match_id == reference.id
        if reference.kind is EntryKind.MERCHANT_DEFAULT:
            return ApplicationConflict.ai_default_id == reference.id
        return ApplicationConflict.ai_preference_id == reference.id
    if reference.kind is EntryKind.MATCHING_ENTRY:
        return ApplicationConflict.confirmed_match_id == reference.id
    if reference.kind is EntryKind.MERCHANT_DEFAULT:
        return ApplicationConflict.confirmed_default_id == reference.id
    return ApplicationConflict.confirmed_preference_id == reference.id


async def _conflict(
    session: AsyncSession,
    occurrence_id: int,
    evidence_revision: int,
    outcome_kind: OutcomeKind,
    ai: ConflictCandidate,
    confirmed: ConflictCandidate,
) -> tuple[ApplicationConflict, ApprovalScope]:
    current = ApprovalScope(
        ai.reference,
        ai.revision,
        confirmed.reference,
        confirmed.revision,
        evidence_revision,
        await _merchant_revisions(session, ai, confirmed),
    )
    row = await session.scalar(
        select(ApplicationConflict).where(
            ApplicationConflict.occurrence_id == occurrence_id,
            ApplicationConflict.ai_kind == ai.reference.kind.value,
            _reference_column(ai.reference, ai=True),
            ApplicationConflict.confirmed_kind == confirmed.reference.kind.value,
            _reference_column(confirmed.reference, ai=False),
        )
    )
    if row is None:
        row = ApplicationConflict(
            occurrence_id=occurrence_id,
            ai_kind=ai.reference.kind.value,
            ai_match_id=ai.reference.id
            if ai.reference.kind is EntryKind.MATCHING_ENTRY
            else None,
            ai_default_id=ai.reference.id
            if ai.reference.kind is EntryKind.MERCHANT_DEFAULT
            else None,
            ai_preference_id=ai.reference.id
            if ai.reference.kind is EntryKind.CLASSIFICATION_PREFERENCE
            else None,
            ai_revision=ai.revision,
            confirmed_kind=confirmed.reference.kind.value,
            confirmed_match_id=confirmed.reference.id
            if confirmed.reference.kind is EntryKind.MATCHING_ENTRY
            else None,
            confirmed_default_id=confirmed.reference.id
            if confirmed.reference.kind is EntryKind.MERCHANT_DEFAULT
            else None,
            confirmed_preference_id=confirmed.reference.id
            if confirmed.reference.kind is EntryKind.CLASSIFICATION_PREFERENCE
            else None,
            confirmed_revision=confirmed.revision,
            evidence_revision=evidence_revision,
            outcome_kind=outcome_kind,
            state="pending",
        )
        session.add(row)
        await session.flush()
    approval = await session.get(ApplicationApproval, row.id)
    revisions_changed = (
        row.ai_revision != ai.revision
        or row.confirmed_revision != confirmed.revision
        or row.evidence_revision != evidence_revision
    )
    approval_stale = row.state == "approved" and (
        approval is None
        or not application_is_approved(
            row.state,
            _stored_scope(approval, ai.reference, confirmed.reference),
            current,
        )
    )
    if revisions_changed or approval_stale:
        row.ai_revision = ai.revision
        row.confirmed_revision = confirmed.revision
        row.evidence_revision = evidence_revision
        row.state = "stale"
        row.review_snapshot = None
        if approval is not None:
            await session.delete(approval)
            await session.flush()
    return row, current


async def detect_application_conflicts(
    session: AsyncSession,
    occurrence_id: int,
    evidence_revision: int,
    outcome_kind: OutcomeKind,
    candidates: Sequence[ConflictCandidate],
) -> ConflictResolution:
    """Create or refresh conflicting typed pairs while the caller owns both locks."""
    validate_id(occurrence_id)
    validate_id(evidence_revision)
    if outcome_kind not in ("merchant", "category"):
        raise RuleValidationError("Invalid conflict outcome")
    allowed_kinds = (
        {EntryKind.MATCHING_ENTRY}
        if outcome_kind == "merchant"
        else {EntryKind.MERCHANT_DEFAULT, EntryKind.CLASSIFICATION_PREFERENCE}
    )
    seen: set[RuleReference] = set()
    for candidate in candidates:
        if candidate.reference.kind not in allowed_kinds:
            raise RuleValidationError("Invalid conflict rule kind")
        if candidate.reference in seen:
            raise RuleValidationError("Duplicate conflict candidate")
        seen.add(candidate.reference)
        if (
            type(candidate.origin) is not ProposalOrigin
            or type(candidate.confirmed) is not bool
        ):
            raise RuleValidationError("Invalid conflict provenance")
        validate_id(candidate.revision)
        for merchant_id in candidate.merchant_ids:
            validate_id(merchant_id)
    blocked: list[BlockedAIConflict] = []
    blocked_refs: set[RuleReference] = set()
    pairs: list[ConflictPair] = []
    for ai in (item for item in candidates if item.origin is ProposalOrigin.AI):
        for confirmed in (item for item in candidates if item.confirmed):
            if ai.reference == confirmed.reference or ai.outcome == confirmed.outcome:
                continue
            row, current = await _conflict(
                session, occurrence_id, evidence_revision, outcome_kind, ai, confirmed
            )
            approval = await session.get(ApplicationApproval, row.id)
            scope = (
                _stored_scope(approval, ai.reference, confirmed.reference)
                if approval is not None
                else None
            )
            approved = application_is_approved(row.state, scope, current)
            pairs.append(ConflictPair(row.id, current, row.state, approved))
            if not approved:
                blocked_refs.add(ai.reference)
                blocked.append(
                    BlockedAIConflict(row.id, ai.reference, confirmed.reference)
                )
    return ConflictResolution(
        eligible=tuple(
            item for item in candidates if item.reference not in blocked_refs
        ),
        blocked=tuple(blocked),
        pairs=tuple(pairs),
    )
