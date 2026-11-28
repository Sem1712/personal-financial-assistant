import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from personal_financial_assistant.infrastructure.database import PinnedConnectionBusy
from personal_financial_assistant.rules.storage import (
    RulesCommitUnknown,
    RulesLockTimeout,
    RulesStorageError,
    rules_transaction,
)


@pytest.mark.asyncio
async def test_rules_transaction_rolls_back_cancellation(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    entered = asyncio.Event()
    try:

        async def write_then_wait() -> None:
            async with rules_transaction(engine) as session:
                await session.execute(
                    text("INSERT INTO merchant (canonical_name) VALUES ('synthetic')")
                )
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(write_then_wait())
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM merchant")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rules_commit_response_loss_is_unknown(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(migrated_url)
    commit = AsyncSession.commit

    async def committed_then_disconnected(session: AsyncSession) -> None:
        await commit(session)
        raise OSError("private connection detail")

    monkeypatch.setattr(AsyncSession, "commit", committed_then_disconnected)
    try:
        with pytest.raises(RulesCommitUnknown, match="read current state") as error:
            async with rules_transaction(engine) as session:
                await session.execute(
                    text("INSERT INTO merchant (canonical_name) VALUES ('synthetic')")
                )
        assert "private connection detail" not in str(error.value)
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM merchant")) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pinned_connection_is_not_committed_when_already_active(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(
                text("INSERT INTO merchant (canonical_name) VALUES ('synthetic')")
            )
            with pytest.raises(PinnedConnectionBusy):
                async with rules_transaction(connection):
                    pytest.fail("active transaction must not be used")
            await transaction.rollback()
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM merchant")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_idle_pinned_connection_remains_owned_by_caller(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            async with rules_transaction(connection) as session:
                await session.execute(
                    text("INSERT INTO merchant (canonical_name) VALUES ('synthetic')")
                )
            assert not connection.closed
            assert not connection.in_transaction()
            assert await connection.scalar(text("SELECT count(*) FROM merchant")) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_storage_errors_are_sanitized_and_rolled_back(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        with pytest.raises(RulesStorageError) as error:
            async with rules_transaction(engine) as session:
                await session.execute(
                    text("INSERT INTO merchant (canonical_name) VALUES ('synthetic')")
                )
                await session.execute(
                    text("INSERT INTO merchant (canonical_name) VALUES ('')")
                )
        assert "synthetic" not in str(error.value)
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM merchant")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_configuration_lock_timeout_is_reported(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as blocker:
            await blocker.execute(
                text("SELECT id FROM rules_configuration WHERE id = 1 FOR UPDATE")
            )
            with pytest.raises(RulesLockTimeout):
                async with rules_transaction(engine):
                    pytest.fail("locked configuration must not be acquired")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_configuration_lock_precedes_occurrence_lock(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
                )
            )
        async with engine.begin() as blocker:
            await blocker.execute(
                text("SELECT id FROM rules_configuration WHERE id = 1 FOR UPDATE")
            )
            entered = asyncio.Event()

            async def waiting_rules_transaction() -> None:
                async with rules_transaction(engine, occurrence_id=1):
                    entered.set()

            task = asyncio.create_task(waiting_rules_transaction())
            try:

                async def wait_for_configuration_waiter() -> None:
                    while True:
                        async with engine.connect() as observer:
                            waiting = await observer.scalar(
                                text(
                                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                    "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock' "
                                    "AND query LIKE '%rules_configuration%FOR UPDATE%'"
                                )
                            )
                        if waiting:
                            return
                        await asyncio.sleep(0.02)

                await asyncio.wait_for(wait_for_configuration_waiter(), 3)
                async with engine.begin() as probe:
                    await probe.execute(text("SET LOCAL lock_timeout = '1s'"))
                    await probe.execute(
                        text(
                            "SELECT id FROM transaction_occurrence WHERE id = 1 FOR UPDATE"
                        )
                    )
                assert not entered.is_set()
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
    finally:
        await engine.dispose()
