import asyncio
import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from personal_financial_assistant.infrastructure.models import (
    OccurrenceEvidenceRevision,
    RuleEvaluationWork,
    TransactionClassification,
)
from personal_financial_assistant.rules import (
    MatchingEntryInput,
    MatchKind,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    create_matching_entry,
    create_merchant,
    create_preference,
    work,
)
from personal_financial_assistant.rules.storage import (
    RulesCommitUnknown,
    RulesStorageError,
)


@pytest.mark.asyncio
async def test_failed_and_unknown_work_are_inspectable_and_retryable(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(migrated_url)
    correlation_id = uuid4()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) "
                    "SELECT n, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed' FROM generate_series(1, 3) AS n"
                )
            )
            await connection.execute(
                insert(RuleEvaluationWork),
                [
                    {
                        "occurrence_id": n,
                        "import_correlation_id": correlation_id,
                        "state": "pending",
                    }
                    for n in range(1, 4)
                ],
            )

        async def fail(*_args: object) -> None:
            raise RulesStorageError("private data")

        with monkeypatch.context() as patch:
            patch.setattr(work, "apply_evaluation_in_session", fail)
            failed = await work.retry_work(engine, [1])
        assert failed.failed == 1
        assert failed.items[0].error_code == "evaluation_failed"
        records = await work.inspect_work(engine, import_correlation_id=correlation_id)
        assert [record.state for record in records] == ["failed", "pending", "pending"]
        assert records[0].outcome is None

        async def unknown(*_args: object) -> None:
            raise RulesCommitUnknown("private data")

        with monkeypatch.context() as patch:
            patch.setattr(
                "personal_financial_assistant.rules.storage.commit_rules_transaction",
                unknown,
            )
            result = await work.retry_work(engine, [2])
        assert result.unknown == 1
        assert (await work.inspect_work(engine, occurrence_ids=[2]))[
            0
        ].state == "pending"

        with monkeypatch.context() as patch:
            patch.setattr(work, "apply_evaluation_in_session", fail)
            patch.setattr(
                "personal_financial_assistant.rules.storage.commit_rules_transaction",
                unknown,
            )
            status_write = await work.retry_work(engine, [3])
        assert status_write.unknown == 1
        assert status_write.items[0].error_code == "status_write_failed"
        assert (await work.inspect_work(engine, occurrence_ids=[3]))[
            0
        ].state == "pending"

        retried = await work.retry_work(engine, [1, 2])
        assert retried.completed == 2
        again = await work.retry_work(engine, [1])
        assert again.items[0].status == "already_completed"
        records = await work.inspect_work(engine, import_correlation_id=correlation_id)
        assert [record.state for record in records] == [
            "completed",
            "completed",
            "pending",
        ]
        assert records[0].outcome is not None
        assert records[0].outcome["merchant_status"] == "no_match"
        async with engine.connect() as connection:
            assert (
                await connection.execute(select(TransactionClassification))
            ).all() == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["retry", "reapply"])
async def test_cancellation_during_commit_stops_the_batch(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    engine = create_async_engine(migrated_url)
    entered = asyncio.Event()
    original_commit = AsyncSession.commit
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) "
                    "SELECT n, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed' FROM generate_series(1, 2) AS n"
                )
            )
            await connection.execute(
                insert(RuleEvaluationWork),
                [
                    {
                        "occurrence_id": n,
                        "import_correlation_id": uuid4(),
                        "state": "pending",
                    }
                    for n in (1, 2)
                ],
            )

        async def committed_then_wait(session: AsyncSession) -> None:
            await original_commit(session)
            if not entered.is_set():
                entered.set()
                await asyncio.Event().wait()

        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", committed_then_wait)
            action = work.retry_work if operation == "retry" else work.reapply_selected
            task = asyncio.create_task(action(engine, [1, 2]))
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError, match="unknown"):
                await task

        async with engine.connect() as connection:
            revisions = (
                await connection.scalars(
                    select(OccurrenceEvidenceRevision.occurrence_id).order_by(
                        OccurrenceEvidenceRevision.occurrence_id
                    )
                )
            ).all()
            assert list(revisions) == [1]
        records = await work.inspect_work(engine, occurrence_ids=[1, 2])
        assert [record.state for record in records] == (
            ["completed", "pending"] if operation == "retry" else ["pending", "pending"]
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("merchant_conflict", [False, True])
async def test_durable_outcome_preserves_complete_conflict_explanations(
    migrated_url: str, merchant_conflict: bool
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')",
                "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 1, 1)",
                "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', 'shop', 'booked', repeat('b',64), 1)",
                "INSERT INTO occurrence_observation VALUES (1, 1)",
            ):
                await connection.execute(text(statement))
            await connection.execute(
                insert(RuleEvaluationWork),
                {
                    "occurrence_id": 1,
                    "import_correlation_id": uuid4(),
                    "state": "pending",
                },
            )
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "shop")
        )
        await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.SUBSTRING, "shop")
        )
        if merchant_conflict:
            other = await create_merchant(engine, MerchantInput("Other"))
            await create_matching_entry(
                engine, MatchingEntryInput(other.id, MatchKind.ALIAS, "shop")
            )
        for category in ("food", "travel"):
            await create_preference(
                engine,
                PreferenceInput(
                    PreferenceKind.EXACT_DESCRIPTION, category, match_text="shop"
                ),
            )
        summary = await work.retry_work(engine, [1])
        result = summary.items[0].result
        assert result is not None and len(result.category_conflict_candidates) == 2
        record = (await work.inspect_work(engine, occurrence_ids=[1]))[0]
        assert record.outcome is not None
        assert record.outcome["merchant_decision"] == json.loads(
            json.dumps(asdict(result.merchant))
        )
        assert record.outcome["category_conflict_candidates"] == [
            asdict(reference) for reference in result.category_conflict_candidates
        ]
    finally:
        await engine.dispose()
