import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from personal_financial_assistant.infrastructure.models import (
    OccurrenceEvidenceRevision,
    RuleEvaluationOutcome,
    RuleEvaluationWork,
    TransactionClassification,
    TransactionOccurrence,
)
from personal_financial_assistant.ingestion import service
from personal_financial_assistant.ingestion.service import ingest_xlsx
from personal_financial_assistant.rules import (
    PreferenceInput,
    PreferenceKind,
    RulesCommitUnknown,
    RulesStorageError,
    create_preference,
    inspect_work,
    retry_work,
    work,
)
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    update_enrichment,
)
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


@pytest.mark.asyncio
async def test_import_evaluates_only_new_occurrences_and_preserves_existing(
    tmp_path: Path, migrated_url: str
) -> None:
    row = ["01/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "first.xlsx").write_bytes(workbook([HEADINGS, row]))
    engine = create_async_engine(migrated_url)
    try:
        await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "food", match_text="shop"
            ),
        )
        result = await ingest_xlsx(tmp_path, engine)
        assert result.evaluation.completed == 1
        assert (
            result.evaluation.failed
            == result.evaluation.pending
            == result.evaluation.unknown
            == 0
        )
        async with engine.connect() as connection:
            occurrence_id = await connection.scalar(select(TransactionOccurrence.id))
            assert occurrence_id is not None
            assert (
                await connection.scalar(select(RuleEvaluationWork.state)) == "completed"
            )
            assert (
                await connection.scalar(select(RuleEvaluationOutcome.occurrence_id))
                == occurrence_id
            )
            assert (
                await connection.scalar(select(TransactionClassification.value))
                == "food"
            )
            evidence_before = await connection.scalar(
                select(OccurrenceEvidenceRevision.revision)
            )
            assert evidence_before is not None
        repeat = await ingest_xlsx(tmp_path, engine)
        assert repeat.transactions_added == repeat.evaluation.attempted == 0
        (tmp_path / "overlap.xlsx").write_bytes(
            workbook([["new preamble"], HEADINGS, row])
        )
        overlap = await ingest_xlsx(tmp_path, engine)
        assert overlap.transactions_added == overlap.evaluation.attempted == 0
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(OccurrenceEvidenceRevision.revision))
                == evidence_before + 1
            )
            assert (
                await connection.scalar(select(TransactionClassification.value))
                == "food"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["evaluation", "unknown"])
async def test_import_survives_evaluation_failure_and_remains_recoverable(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    row = ["01/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "first.xlsx").write_bytes(workbook([HEADINGS, row]))
    engine = create_async_engine(migrated_url)
    try:

        async def fail(*_args: object) -> None:
            if failure == "evaluation":
                raise RulesStorageError("private payload")
            raise RulesCommitUnknown("private payload")

        with monkeypatch.context() as patch:
            if failure == "evaluation":
                patch.setattr(work, "apply_evaluation_in_session", fail)
            else:
                patch.setattr(
                    "personal_financial_assistant.rules.storage.commit_rules_transaction",
                    fail,
                )
            result = await ingest_xlsx(tmp_path, engine)
        assert result.transactions_added == 1
        assert result.evaluation.failed == int(failure == "evaluation")
        assert result.evaluation.unknown == int(failure == "unknown")
        assert result.correlation_id is not None
        records = await inspect_work(
            engine, import_correlation_id=result.correlation_id
        )
        assert len(records) == 1
        assert records[0].state == ("failed" if failure == "evaluation" else "pending")
        assert records[0].outcome is None
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(TransactionOccurrence.id))
                == records[0].occurrence_id
            )
        assert (await retry_work(engine, [records[0].occurrence_id])).completed == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unresolved_new_occurrence_receives_a_completed_no_match_outcome(
    tmp_path: Path, migrated_url: str
) -> None:
    row = ["01/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "first.xlsx").write_bytes(workbook([HEADINGS, row]))
    engine = create_async_engine(migrated_url)
    try:
        initial = await ingest_xlsx(tmp_path, engine)
        assert initial.evaluation.completed == 1
        (tmp_path / "two.xlsx").write_bytes(workbook([HEADINGS, row, row]))
        result = await ingest_xlsx(tmp_path, engine)
        assert result.transactions_added == result.evaluation.completed == 1
        assert result.correlation_id is not None
        records = await inspect_work(
            engine, import_correlation_id=result.correlation_id
        )
        assert len(records) == 1 and records[0].state == "completed"
        assert records[0].outcome is not None
        assert records[0].outcome["merchant_status"] == "no_match"
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    select(TransactionOccurrence.reconciliation_state).where(
                        TransactionOccurrence.id == records[0].occurrence_id
                    )
                )
                == "unresolved"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_booking_reconciliation_does_not_reclassify_existing_occurrence(
    tmp_path: Path, migrated_url: str
) -> None:
    pending = ["01/01/2022", "shop", "", "TEST", "NON CONTABILIZZATO", "", "EUR", -5]
    booked = ["01/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "pending.xlsx").write_bytes(workbook([HEADINGS, pending]))
    engine = create_async_engine(migrated_url)
    try:
        await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "food", match_text="shop"
            ),
        )
        await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            occurrence_id = await connection.scalar(select(TransactionOccurrence.id))
        assert occurrence_id is not None
        await update_enrichment(
            engine,
            occurrence_id,
            EnrichmentUpdate.model_validate(
                {
                    "category": {
                        "value": "manual",
                        "status": "confirmed",
                        "source": "user",
                    }
                }
            ),
        )
        (tmp_path / "booked.xlsx").write_bytes(workbook([HEADINGS, booked]))
        result = await ingest_xlsx(tmp_path, engine)
        assert result.transactions_updated == 1
        assert result.transactions_added == result.evaluation.attempted == 0
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(OccurrenceEvidenceRevision.revision))
                == 2
            )
            assert (
                await connection.scalar(select(TransactionClassification.value))
                == "manual"
            )
        assert len(await inspect_work(engine)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_interruption_after_import_commit_leaves_pending_work(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = ["01/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "first.xlsx").write_bytes(workbook([HEADINGS, row]))
    engine = create_async_engine(migrated_url)
    correlation_id = uuid4()
    try:

        async def interrupted(*_args: object) -> None:
            raise asyncio.CancelledError

        with monkeypatch.context() as patch:
            patch.setattr(service, "retry_work", interrupted)
            with pytest.raises(asyncio.CancelledError):
                await ingest_xlsx(
                    tmp_path, engine, import_correlation_id=correlation_id
                )
        records = await inspect_work(engine, import_correlation_id=correlation_id)
        assert len(records) == 1 and records[0].state == "pending"
        assert (await inspect_work(engine))[0].occurrence_id == records[0].occurrence_id
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(TransactionOccurrence.id))
                == records[0].occurrence_id
            )
        assert (await retry_work(engine, [records[0].occurrence_id])).completed == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_evaluation_commit_stops_import_evaluation(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        ["01/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -5],
        ["02/01/2022", "shop", "", "TEST", "CONTABILIZZATO", "", "EUR", -6],
    ]
    (tmp_path / "import.xlsx").write_bytes(workbook([HEADINGS, *rows]))
    engine = create_async_engine(migrated_url)
    correlation_id = uuid4()
    entered = asyncio.Event()
    original_commit = AsyncSession.commit

    async def committed_then_wait(session: AsyncSession) -> None:
        await original_commit(session)
        if not entered.is_set():
            entered.set()
            await asyncio.Event().wait()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", committed_then_wait)
            task = asyncio.create_task(
                ingest_xlsx(tmp_path, engine, import_correlation_id=correlation_id)
            )
            await asyncio.wait_for(entered.wait(), 10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError, match="unknown"):
                await task
        records = await inspect_work(engine, import_correlation_id=correlation_id)
        assert [record.state for record in records] == ["completed", "pending"]
    finally:
        await engine.dispose()
