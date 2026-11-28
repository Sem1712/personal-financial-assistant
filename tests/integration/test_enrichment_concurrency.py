import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from personal_financial_assistant.transactions import (
    EnrichmentCommitUnknown,
    EnrichmentLockTimeout,
    EnrichmentStorageError,
    EnrichmentUpdate,
    OccurrenceNotFound,
    apply_enrichment_in_session,
    lock_occurrence,
    update_enrichment,
)
from personal_financial_assistant.transactions.service import detail


@pytest_asyncio.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
            )
        )
    yield engine
    await engine.dispose()


def patch(**fields: object) -> EnrichmentUpdate:
    return EnrichmentUpdate.model_validate(fields)


def classification(value: str, source: str = "user") -> dict[str, str]:
    return {"value": value, "status": "confirmed", "source": source}


@pytest.mark.asyncio
async def test_session_enrichment_obeys_caller_transaction(engine: AsyncEngine) -> None:
    await update_enrichment(
        engine,
        1,
        patch(transaction_type=classification("expense"), user_annotation="note"),
    )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await lock_occurrence(session, 1)
        result = await apply_enrichment_in_session(
            session, 1, patch(category=classification("food", "rule"))
        )
        assert result.category.value == "food"
        assert result.transaction_type.value == "expense"
        assert result.user_annotation == "note"
        before_commit = await detail(engine, 1)
        assert before_commit is not None
        assert before_commit.enrichment.category.status == "unclassified"
        await session.rollback()

    after_rollback = await detail(engine, 1)
    assert after_rollback is not None
    assert after_rollback.enrichment.category.status == "unclassified"
    assert after_rollback.enrichment.transaction_type.value == "expense"
    assert after_rollback.enrichment.user_annotation == "note"

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await lock_occurrence(session, 1)
        await apply_enrichment_in_session(
            session, 1, patch(category=classification("food", "rule"))
        )
        await session.commit()
    after_commit = await detail(engine, 1)
    assert after_commit is not None
    assert after_commit.enrichment.category.value == "food"
    assert after_commit.enrichment.category.source == "rule"


@pytest.mark.asyncio
async def test_session_lock_reports_missing_occurrence(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        with pytest.raises(OccurrenceNotFound):
            await lock_occurrence(session, 999)


@pytest.mark.asyncio
async def test_concurrent_disjoint_updates_and_replacement(engine: AsyncEngine) -> None:
    await asyncio.gather(
        update_enrichment(engine, 1, patch(category=classification("groceries"))),
        update_enrichment(engine, 1, patch(transaction_type=classification("expense"))),
    )
    result = await update_enrichment(
        engine, 1, patch(category=classification("housing", "ai"))
    )
    assert result.category.value == "housing"
    assert result.category.source == "ai"
    assert result.category.confidence is None
    assert result.transaction_type.value == "expense"


@pytest.mark.asyncio
@pytest.mark.parametrize("confidence", [None, "37.25"])
async def test_automated_replacement_replaces_all_metadata(
    engine: AsyncEngine, confidence: str | None
) -> None:
    await update_enrichment(
        engine,
        1,
        patch(
            category={
                "value": "old",
                "status": "confirmed",
                "source": "user",
                "confidence": "99.99",
            }
        ),
    )
    await update_enrichment(
        engine,
        1,
        patch(
            category={
                "value": "new",
                "status": "provisional",
                "source": "ai",
                "confidence": confidence,
            }
        ),
    )
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.category.model_dump() == {
        "value": "new",
        "status": "provisional",
        "source": "ai",
        "confidence": confidence,
    }


async def wait_for_lock_waiters(engine: AsyncEngine, count: int) -> None:
    async def wait() -> None:
        while True:
            async with engine.connect() as conn:
                waiting = await conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                        "AND wait_event_type = 'Lock' AND query LIKE '%FOR UPDATE%'"
                    )
                )
            if waiting is not None and waiting >= count:
                return
            await asyncio.sleep(0.02)

    await asyncio.wait_for(wait(), 3)


@pytest.mark.asyncio
async def test_same_field_writers_commit_in_lock_order(engine: AsyncEngine) -> None:
    async with engine.begin() as lock:
        await lock.execute(
            text("SELECT id FROM transaction_occurrence WHERE id = 1 FOR UPDATE")
        )
        first = asyncio.create_task(
            update_enrichment(engine, 1, patch(category=classification("first")))
        )
        await wait_for_lock_waiters(engine, 1)
        second = asyncio.create_task(
            update_enrichment(
                engine, 1, patch(category=classification("second", "rule"))
            )
        )
        await wait_for_lock_waiters(engine, 2)
    first_result, second_result = await asyncio.gather(first, second)
    assert first_result.category.value == "first"
    assert second_result.category.value == "second"
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.category.value == "second"
    assert result.enrichment.category.source == "rule"


@pytest.mark.asyncio
async def test_invalid_multi_field_patch_changes_nothing(engine: AsyncEngine) -> None:
    await update_enrichment(engine, 1, patch(category=classification("original")))
    with pytest.raises(ValidationError):
        patch(
            category=classification("replacement"),
            budget_treatment=classification("not valid"),
        )
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.category.value == "original"
    assert result.enrichment.budget_treatment.status == "unclassified"


@pytest.mark.asyncio
async def test_lock_timeout_and_cancel_leave_no_change(engine: AsyncEngine) -> None:
    async with engine.begin() as lock:
        await lock.execute(
            text("SELECT id FROM transaction_occurrence WHERE id = 1 FOR UPDATE")
        )
        with pytest.raises(EnrichmentLockTimeout):
            await update_enrichment(engine, 1, patch(category=classification("food")))
        task = asyncio.create_task(
            update_enrichment(engine, 1, patch(category=classification("food")))
        )
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.category.status == "unclassified"


@pytest.mark.asyncio
async def test_commit_disconnect_is_unknown_and_state_can_be_read(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = AsyncSession.commit

    async def committed_then_disconnected(session: AsyncSession) -> None:
        await commit(session)
        raise OSError("sensitive connection details")

    monkeypatch.setattr(AsyncSession, "commit", committed_then_disconnected)
    with pytest.raises(EnrichmentCommitUnknown, match="read current state") as error:
        await update_enrichment(engine, 1, patch(category=classification("food")))
    assert "sensitive" not in str(error.value)
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.category.value == "food"


@pytest.mark.asyncio
async def test_flush_failure_rolls_back_without_exposing_values(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    flush = AsyncSession.flush

    async def failed_after_flush(
        session: AsyncSession, *args: object, **kwargs: object
    ) -> None:
        await flush(session)
        raise SQLAlchemyError("private note")

    monkeypatch.setattr(AsyncSession, "flush", failed_after_flush)
    with pytest.raises(EnrichmentStorageError) as error:
        await update_enrichment(engine, 1, patch(user_annotation="private note"))
    assert "private note" not in str(error.value)
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.user_annotation is None


@pytest.mark.asyncio
async def test_cancel_during_commit_is_unknown(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def interrupted(_session: AsyncSession) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(AsyncSession, "commit", interrupted)
    with pytest.raises(EnrichmentCommitUnknown):
        await update_enrichment(engine, 1, patch(category=classification("food")))
    result = await detail(engine, 1)
    assert result is not None
    assert result.enrichment.category.status == "unclassified"


@pytest.mark.asyncio
async def test_rollback_error_is_sanitized(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failed_rollback(_session: AsyncSession) -> None:
        raise SQLAlchemyError("private connection")

    monkeypatch.setattr(AsyncSession, "rollback", failed_rollback)
    with pytest.raises(EnrichmentStorageError, match="roll back") as error:
        await update_enrichment(engine, 2, patch(category=classification("food")))
    assert "private" not in str(error.value)
