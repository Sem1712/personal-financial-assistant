import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from personal_financial_assistant.rules.overrides import (
    clear_override,
    inspect_override,
    set_override,
)
from personal_financial_assistant.rules.storage import RulesStorageError
from personal_financial_assistant.transactions import (
    EnrichmentResult,
    EnrichmentUpdate,
    OccurrenceNotFound,
)
from personal_financial_assistant.transactions.service import detail


@pytest.mark.asyncio
async def test_override_owns_only_occurrence_lock_and_clear_preserves_category(
    migrated_url: str,
) -> None:
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
            first = await asyncio.wait_for(set_override(engine, 1, "food"), 2)
        second = await set_override(engine, 1, "other")
        assert second.revision == first.revision + 1
        assert await inspect_override(engine, 1) == second
        assert await clear_override(engine, 1)
        assert await inspect_override(engine, 1) is None
        result = await detail(engine, 1)
        assert result is not None
        assert result.enrichment.category.value == "other"
        assert result.enrichment.category.source == "user"
        assert not await clear_override(engine, 1)
        with pytest.raises(OccurrenceNotFound):
            await inspect_override(engine, 999)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_override_failure_rolls_back_override_and_category(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
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

        async def fail_after_flush(
            session: AsyncSession, occurrence_id: int, update: EnrichmentUpdate
        ) -> EnrichmentResult:
            await session.flush()
            raise OSError("private payload")

        monkeypatch.setattr(
            "personal_financial_assistant.rules.overrides.apply_enrichment_in_session",
            fail_after_flush,
        )
        with pytest.raises(RulesStorageError) as error:
            await set_override(engine, 1, "food")
        assert "private payload" not in str(error.value)
        assert await inspect_override(engine, 1) is None
        result = await detail(engine, 1)
        assert result is not None
        assert result.enrichment.category.status == "unclassified"
    finally:
        await engine.dispose()
