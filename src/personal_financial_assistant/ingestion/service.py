"""Coordinate batch validation and atomic PostgreSQL persistence."""

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from personal_financial_assistant.infrastructure.database import (
    PinnedConnectionBusy,
    PinnedConnectionLost,
    session_scope,
)
from personal_financial_assistant.infrastructure.models import (
    OccurrenceEvidenceRevision,
    RuleEvaluationWork,
    SelectedAccount,
    SourceFile,
    TransactionObservation,
    TransactionOccurrence,
    occurrence_observation,
)
from personal_financial_assistant.ingestion.identity import Evidence, plan_group
from personal_financial_assistant.ingestion.worker_client import WorkbookWorker
from personal_financial_assistant.ingestion.xlsx_reader import (
    FileSnapshot,
    Observation,
    ParsedFile,
    WorkbookError,
    check_snapshots,
    discover_workbooks,
    read_workbook,
)
from personal_financial_assistant.rules import (
    MAX_SELECTION,
    EvaluationItem,
    EvaluationSummary,
    RulesCommitUnknown,
    RulesStorageError,
    RuleValidationError,
    retry_work,
    summarize,
    validate_correlation_id,
)
from personal_financial_assistant.transactions import lock_occurrence


class IngestionError(Exception):
    """A sanitized import failure."""


class InvalidWorkbook(IngestionError):
    """A source workbook is invalid, unreadable, or changed."""


class AccountMismatch(IngestionError):
    """Source accounts are inconsistent or differ from the selected account."""


class ImportInProgress(IngestionError):
    """Another ingestion transaction holds the import lock."""


@dataclass(frozen=True)
class ImportResult:
    files_seen: int
    files_processed: int
    files_unchanged: int
    rows_read: int
    transactions_added: int
    transactions_updated: int
    observations_unchanged: int
    unresolved_observations: int
    errors: tuple[str, ...] = ()
    correlation_id: UUID | None = None
    evaluation: EvaluationSummary = field(default_factory=EvaluationSummary)


def _candidate_key(account_id: int, observation: Observation) -> str:
    value = (
        f"{account_id}\0{observation.transaction_date.isoformat()}\0"
        f"{observation.amount_minor}\0{observation.currency}"
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def ingest_xlsx(
    directory: Path,
    engine: AsyncEngine | AsyncConnection,
    *,
    snapshots: Sequence[FileSnapshot] | None = None,
    worker: WorkbookWorker | None = None,
    import_correlation_id: UUID | None = None,
) -> ImportResult:
    """Reconcile a batch atomically, optionally using an owned UI worker and connection.

    The caller owns the worker and any pinned connection. A pinned connection must
    not have an active transaction when ingestion starts.
    """
    try:
        correlation_id = validate_correlation_id(
            import_correlation_id if import_correlation_id is not None else uuid4()
        )
    except RuleValidationError:
        raise IngestionError("Invalid import correlation ID") from None
    if snapshots is None:
        snapshots = (
            await worker.discover(directory)
            if worker is not None
            else await discover_workbooks(directory)
        )
    parsed: list[ParsedFile] = []
    for ordinal, snapshot in enumerate(snapshots, 1):
        try:
            parsed.append(
                await worker.read(snapshot)
                if worker is not None
                else await read_workbook(snapshot)
            )
        except WorkbookError as exc:
            raise InvalidWorkbook(f"file {ordinal}: {exc}") from None
    accounts = {
        source.account_reference
        for source in parsed
        if source.account_reference is not None
    }
    if len(accounts) > 1:
        raise AccountMismatch("multiple accounts")
    if not parsed:
        try:
            if worker is not None:
                await worker.verify(snapshots)
            else:
                await check_snapshots(snapshots)
        except WorkbookError as exc:
            raise InvalidWorkbook(str(exc)) from None
        return ImportResult(
            len(snapshots),
            len(snapshots),
            0,
            0,
            0,
            0,
            0,
            0,
            correlation_id=correlation_id,
        )
    account_reference = next(iter(accounts), None)
    new_occurrence_ids: list[int] = []
    async with session_scope(engine) as session:
        locked = await session.scalar(select(func.pg_try_advisory_xact_lock(7718257)))
        if not locked:
            raise ImportInProgress("another import is in progress")
        existing_account = await session.scalar(select(SelectedAccount))
        if (
            account_reference is not None
            and existing_account
            and existing_account.account_reference != account_reference
        ):
            raise AccountMismatch("account does not match previous imports")
        account = existing_account
        if account is None and account_reference is not None:
            account = SelectedAccount(account_reference=account_reference)
            session.add(account)
            await session.flush()
        seen_sources: set[str] = set()
        groups: defaultdict[str, list[TransactionObservation]] = defaultdict(list)
        inserted = 0
        updated = 0
        unchanged_files = 0
        unchanged_rows = 0
        for source in parsed:
            existing_source = await session.get(SourceFile, source.sha256)
            if source.sha256 in seen_sources or existing_source is not None:
                if (
                    existing_source is not None
                    and existing_source.account_id is None
                    and source.account_reference is not None
                    and account is not None
                ):
                    existing_source.account_id = account.id
                unchanged_files += 1
                unchanged_rows += len(source.observations)
                continue
            seen_sources.add(source.sha256)
            session.add(
                SourceFile(
                    sha256=source.sha256,
                    account_id=(
                        account.id if source.account_reference and account else None
                    ),
                    transaction_row_count=len(source.observations),
                )
            )
            await session.flush()
            if not source.observations:
                continue
            if account is None:
                raise InvalidWorkbook("missing account for transaction rows")
            ordinals: defaultdict[str, int] = defaultdict(int)
            for observation in source.observations:
                key = _candidate_key(account.id, observation)
                ordinals[key] += 1
                record = TransactionObservation(
                    source_file_sha256=source.sha256,
                    sheet_index=observation.sheet_index,
                    row_number=observation.row_number,
                    account_id=account.id,
                    transaction_date=observation.transaction_date,
                    amount_minor=observation.amount_minor,
                    currency=observation.currency,
                    operation=observation.operation,
                    details=observation.details,
                    booking_status=observation.booking_status,
                    category=observation.category,
                    candidate_key=key,
                    occurrence_ordinal=ordinals[key],
                )
                session.add(record)
                await session.flush()
                groups[key].append(record)
        for records in groups.values():
            first = records[0]
            existing = list(
                (
                    await session.scalars(
                        select(TransactionOccurrence)
                        .where(
                            TransactionOccurrence.account_id == first.account_id,
                            TransactionOccurrence.transaction_date
                            == first.transaction_date,
                            TransactionOccurrence.amount_minor == first.amount_minor,
                            TransactionOccurrence.currency == first.currency,
                        )
                        .order_by(TransactionOccurrence.id)
                    )
                ).all()
            )
            plan = plan_group(
                [(item.id, item.booking_status) for item in existing],
                [
                    Evidence(item.id, item.source_file_sha256, item.booking_status)
                    for item in records
                ],
            )
            by_id = {item.id: item for item in records}
            new_occurrences: list[TransactionOccurrence] = []
            for record_id, status in plan.create:
                record = by_id[record_id] if record_id is not None else first
                occurrence = TransactionOccurrence(
                    account_id=first.account_id,
                    transaction_date=record.transaction_date,
                    amount_minor=record.amount_minor,
                    currency=record.currency,
                    booking_status=status,
                    reconciliation_state=(
                        "unresolved"
                        if record_id is None
                        else "pending-only"
                        if status == "pending"
                        else "confirmed"
                    ),
                )
                session.add(occurrence)
                await session.flush()
                new_occurrences.append(occurrence)
                new_occurrence_ids.append(occurrence.id)
                session.add(
                    OccurrenceEvidenceRevision(occurrence_id=occurrence.id, revision=1)
                )
                session.add(
                    RuleEvaluationWork(
                        occurrence_id=occurrence.id,
                        import_correlation_id=correlation_id,
                        state="pending",
                    )
                )
                if record_id is not None:
                    await session.execute(
                        insert(occurrence_observation).values(
                            occurrence_id=occurrence.id, observation_id=record.id
                        )
                    )
                inserted += 1
            affected_occurrences = {
                occurrence_id for occurrence_id, _ in (*plan.updates, *plan.links)
            }
            for occurrence_id in sorted(affected_occurrences):
                await lock_occurrence(session, occurrence_id)
            for occurrence_id, status in plan.updates:
                occurrence = next(item for item in existing if item.id == occurrence_id)
                occurrence.booking_status = status
                occurrence.reconciliation_state = "confirmed"
                updated += 1
            for occurrence_id, observation_id in plan.links:
                await session.execute(
                    insert(occurrence_observation).values(
                        occurrence_id=occurrence_id, observation_id=observation_id
                    )
                )
            for occurrence_id in {occurrence_id for occurrence_id, _ in plan.links}:
                evidence = await session.get(OccurrenceEvidenceRevision, occurrence_id)
                if evidence is None:
                    session.add(
                        OccurrenceEvidenceRevision(
                            occurrence_id=occurrence_id, revision=2
                        )
                    )
                else:
                    evidence.revision += 1
            for index, observation_id in plan.new_links:
                await session.execute(
                    insert(occurrence_observation).values(
                        occurrence_id=new_occurrences[index].id,
                        observation_id=observation_id,
                    )
                )
        unresolved = await session.scalar(
            select(func.count())
            .select_from(TransactionObservation)
            .where(
                ~select(occurrence_observation.c.observation_id)
                .where(
                    occurrence_observation.c.observation_id == TransactionObservation.id
                )
                .exists()
            )
        )
        try:
            if worker is not None:
                await worker.verify(snapshots)
            else:
                await check_snapshots(snapshots)
        except WorkbookError as exc:
            raise InvalidWorkbook(str(exc)) from None
    evaluation_items: list[EvaluationItem] = []
    for offset in range(0, len(new_occurrence_ids), MAX_SELECTION):
        selected = new_occurrence_ids[offset : offset + MAX_SELECTION]
        try:
            batch = await retry_work(engine, selected)
        except (
            RulesStorageError,
            RulesCommitUnknown,
            PinnedConnectionBusy,
            PinnedConnectionLost,
        ):
            evaluation_items.extend(
                EvaluationItem(
                    occurrence_id, "unknown", error_code="evaluation_unavailable"
                )
                for occurrence_id in selected
            )
        else:
            evaluation_items.extend(batch.items)
    return ImportResult(
        files_seen=len(snapshots),
        files_processed=len(seen_sources),
        files_unchanged=unchanged_files,
        rows_read=sum(len(source.observations) for source in parsed),
        transactions_added=inserted,
        transactions_updated=updated,
        observations_unchanged=unchanged_rows,
        unresolved_observations=unresolved or 0,
        correlation_id=correlation_id,
        evaluation=summarize(evaluation_items),
    )
