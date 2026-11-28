"""Explicit reapplication and durable, individually recoverable import work."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.database import (
    PinnedConnectionBusy,
    PinnedConnectionLost,
)
from personal_financial_assistant.infrastructure.models import (
    RuleEvaluationOutcome,
    RuleEvaluationWork,
)
from personal_financial_assistant.transactions import OccurrenceNotFound

from .application import PreparedApplication, prepare_application
from .evaluation import apply_evaluation_in_session, evaluate_in_session
from .storage import RulesCommitUnknown, RulesStorageError, rules_transaction
from .types import (
    CategoryApplied,
    CategoryOverride,
    EvaluationResult,
    MerchantResolved,
    RuleReference,
    RuleValidationError,
    validate_correlation_id,
    validate_id,
)

type Database = AsyncEngine | AsyncConnection
type ItemStatus = Literal[
    "completed", "failed", "pending", "unknown", "not_found", "already_completed"
]
MAX_SELECTION = 500


@dataclass(frozen=True)
class EvaluationItem:
    occurrence_id: int
    status: ItemStatus
    result: EvaluationResult | None = field(default=None, repr=False)
    error_code: str | None = None


@dataclass(frozen=True)
class EvaluationSummary:
    attempted: int = 0
    completed: int = 0
    failed: int = 0
    pending: int = 0
    unknown: int = 0
    items: tuple[EvaluationItem, ...] = ()


@dataclass(frozen=True)
class WorkRecord:
    occurrence_id: int
    import_correlation_id: UUID
    state: str
    last_error_code: str | None
    outcome: dict[str, object] | None = field(default=None, repr=False)


def validate_selection(ids: Sequence[int]) -> tuple[int, ...]:
    """Validate a bounded, nonempty selection before starting any transaction."""
    if not ids or len(ids) > MAX_SELECTION:
        raise RuleValidationError("Invalid occurrence selection")
    selected = tuple(ids)
    for occurrence_id in selected:
        validate_id(occurrence_id)
    if len(set(selected)) != len(selected):
        raise RuleValidationError("Duplicate occurrence ID")
    return selected


def summarize(items: Sequence[EvaluationItem]) -> EvaluationSummary:
    """Summarize individual outcomes without treating unknown as success."""
    return EvaluationSummary(
        attempted=sum(
            item.status not in ("pending", "already_completed") for item in items
        ),
        completed=sum(
            item.status in ("completed", "already_completed") for item in items
        ),
        failed=sum(item.status in ("failed", "not_found") for item in items),
        pending=sum(item.status == "pending" for item in items),
        unknown=sum(item.status == "unknown" for item in items),
        items=tuple(items),
    )


def _reference(reference: RuleReference) -> dict[str, object]:
    return {"kind": reference.kind.value, "id": reference.id}


async def _store_outcome(
    session: AsyncSession, prepared: PreparedApplication, work: RuleEvaluationWork
) -> None:
    result = prepared.result
    merchant_id = (
        result.merchant.merchant_id
        if isinstance(result.merchant, MerchantResolved)
        else None
    )
    winners: list[dict[str, object]]
    if isinstance(result.category, CategoryApplied):
        winners = [_reference(reference) for reference in result.category.winning_rules]
    elif isinstance(result.category, CategoryOverride):
        winners = [{"kind": "override", "id": result.occurrence_id}]
    else:
        winners = []
    outcome = await session.get(RuleEvaluationOutcome, work.occurrence_id)
    if outcome is None:
        outcome = RuleEvaluationOutcome(occurrence_id=work.occurrence_id)
        session.add(outcome)
    outcome.evidence_revision = result.evidence_revision
    outcome.merchant_status = result.merchant.status
    outcome.merchant_id = merchant_id
    outcome.matching_candidates = [
        _reference(reference) for reference in prepared.matching_candidates
    ]
    outcome.category_decision = asdict(result.category)
    outcome.merchant_decision = asdict(result.merchant)
    outcome.category_conflict_candidates = [
        _reference(reference) for reference in result.category_conflict_candidates
    ]
    outcome.winning_references = winners
    outcome.blocked_ai_conflicts = [
        asdict(conflict) for conflict in result.blocked_ai_conflicts
    ]
    work.state = "completed"
    work.last_error_code = None


def _outcome_record(outcome: RuleEvaluationOutcome | None) -> dict[str, object] | None:
    if outcome is None:
        return None
    return {
        "evidence_revision": outcome.evidence_revision,
        "merchant_status": outcome.merchant_status,
        "merchant_id": outcome.merchant_id,
        "merchant_decision": outcome.merchant_decision,
        "matching_candidates": outcome.matching_candidates,
        "category_decision": outcome.category_decision,
        "category_conflict_candidates": outcome.category_conflict_candidates,
        "winning_references": outcome.winning_references,
        "blocked_ai_conflicts": outcome.blocked_ai_conflicts,
    }


async def inspect_work(
    bind: Database,
    *,
    occurrence_ids: Sequence[int] | None = None,
    import_correlation_id: UUID | None = None,
) -> tuple[WorkRecord, ...]:
    """Inspect work and outcomes, optionally filtered by IDs or correlation."""
    if occurrence_ids is not None and import_correlation_id is not None:
        raise RuleValidationError("Select work by IDs or import correlation")
    ids = validate_selection(occurrence_ids) if occurrence_ids is not None else None
    if import_correlation_id is not None:
        validate_correlation_id(import_correlation_id)
    async with rules_transaction(bind) as session:
        query = select(RuleEvaluationWork).order_by(RuleEvaluationWork.occurrence_id)
        if ids is not None:
            query = query.where(RuleEvaluationWork.occurrence_id.in_(ids))
        elif import_correlation_id is not None:
            query = query.where(
                RuleEvaluationWork.import_correlation_id == import_correlation_id
            )
        rows = (await session.scalars(query)).all()
        records: list[WorkRecord] = []
        for row in rows:
            outcome = await session.get(RuleEvaluationOutcome, row.occurrence_id)
            records.append(
                WorkRecord(
                    row.occurrence_id,
                    row.import_correlation_id,
                    row.state,
                    row.last_error_code,
                    _outcome_record(outcome),
                )
            )
        return tuple(records)


async def reapply_selected(
    bind: Database, occurrence_ids: Sequence[int]
) -> EvaluationSummary:
    """Evaluate only the requested occurrences, independently and sequentially."""
    selected = validate_selection(occurrence_ids)
    items: list[EvaluationItem] = []
    for occurrence_id in selected:
        try:
            async with rules_transaction(bind, occurrence_id=occurrence_id) as session:
                result = await evaluate_in_session(session, occurrence_id)
        except OccurrenceNotFound:
            items.append(
                EvaluationItem(occurrence_id, "not_found", error_code="not_found")
            )
        except RulesCommitUnknown:
            items.append(
                EvaluationItem(occurrence_id, "unknown", error_code="commit_unknown")
            )
        except (
            RulesStorageError,
            RuleValidationError,
            PinnedConnectionBusy,
            PinnedConnectionLost,
        ):
            items.append(
                EvaluationItem(occurrence_id, "failed", error_code="storage_failure")
            )
        else:
            items.append(EvaluationItem(occurrence_id, "completed", result))
    return summarize(items)


async def _record_failure(bind: Database, occurrence_id: int) -> EvaluationItem:
    try:
        async with rules_transaction(bind, occurrence_id=occurrence_id) as session:
            row = await session.get(RuleEvaluationWork, occurrence_id)
            if row is None:
                return EvaluationItem(
                    occurrence_id, "not_found", error_code="work_not_found"
                )
            if row.state == "completed":
                return EvaluationItem(occurrence_id, "already_completed")
            row.state = "failed"
            row.last_error_code = "evaluation_failed"
    except (
        RulesStorageError,
        RulesCommitUnknown,
        PinnedConnectionBusy,
        PinnedConnectionLost,
    ):
        return EvaluationItem(
            occurrence_id, "unknown", error_code="status_write_failed"
        )
    return EvaluationItem(occurrence_id, "failed", error_code="evaluation_failed")


async def retry_work(
    bind: Database, occurrence_ids: Sequence[int]
) -> EvaluationSummary:
    """Explicitly retry selected pending/failed work, checking state under locks."""
    selected = validate_selection(occurrence_ids)
    items: list[EvaluationItem] = []
    for occurrence_id in selected:
        try:
            async with rules_transaction(bind, occurrence_id=occurrence_id) as session:
                work = await session.get(RuleEvaluationWork, occurrence_id)
                if work is None:
                    item = EvaluationItem(
                        occurrence_id, "not_found", error_code="work_not_found"
                    )
                elif work.state == "completed":
                    item = EvaluationItem(occurrence_id, "already_completed")
                else:
                    prepared = await prepare_application(session, occurrence_id)
                    await apply_evaluation_in_session(session, prepared.result)
                    await _store_outcome(session, prepared, work)
                    item = EvaluationItem(occurrence_id, "completed", prepared.result)
        except OccurrenceNotFound:
            item = EvaluationItem(occurrence_id, "not_found", error_code="not_found")
        except RulesCommitUnknown:
            item = EvaluationItem(occurrence_id, "unknown", error_code="commit_unknown")
        except (
            RulesStorageError,
            RuleValidationError,
            PinnedConnectionBusy,
            PinnedConnectionLost,
        ):
            item = await _record_failure(bind, occurrence_id)
        items.append(item)
    return summarize(items)
