import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    OccurrenceNotFound,
    update_enrichment,
)
from personal_financial_assistant.transactions.service import detail


@pytest.mark.asyncio
async def test_classification_independence_on_reference_set(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) SELECT n, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed' FROM generate_series(1, 100) n"
                )
            )
            await conn.execute(
                text(
                    "UPDATE transaction_occurrence SET booking_status = NULL, reconciliation_state = 'unresolved' WHERE id = 100"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 1, 1)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, transaction_date, amount_minor, currency, booking_status, category, candidate_key, occurrence_ordinal) VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', 'booked', 'bank category', repeat('b',64), 1)"
                )
            )
            await conn.execute(text("INSERT INTO occurrence_observation VALUES (1, 1)"))
        types = ("expense", "income", "transfer", "refund")
        treatments = ("ordinary", "extraordinary", "excluded")
        for occurrence_id in range(1, 101):
            payload = {
                "transaction_type": {
                    "value": types[occurrence_id % 4],
                    "status": "confirmed",
                    "source": "user",
                },
                "category": {
                    "value": "groceries",
                    "status": "provisional",
                    "source": "ai",
                    "confidence": "72.50",
                },
                "budget_treatment": {
                    "value": treatments[occurrence_id % 3],
                    "status": "confirmed",
                    "source": "rule",
                },
            }
            await update_enrichment(
                engine, occurrence_id, EnrichmentUpdate.model_validate(payload)
            )
            result = await detail(engine, occurrence_id)
            assert result is not None
            for dimension in ("transaction_type", "category", "budget_treatment"):
                expected = {
                    **payload[dimension],
                    "confidence": payload[dimension].get("confidence"),
                }
                assert getattr(result.enrichment, dimension).model_dump() == expected
        await update_enrichment(
            engine, 1, EnrichmentUpdate.model_validate({"category": None})
        )
        first = await detail(engine, 1)
        second = await detail(engine, 2)
        assert first is not None and second is not None
        assert first.enrichment.category.status == "unclassified"
        assert first.enrichment.category.source is None
        assert second.enrichment.category.value == "groceries"
        assert first.enrichment.transaction_type.value == types[1]
        assert first.observations[0].category == "bank category"
        with pytest.raises(OccurrenceNotFound):
            await update_enrichment(
                engine, 101, EnrichmentUpdate.model_validate({"category": None})
            )
        await update_enrichment(
            engine,
            1,
            EnrichmentUpdate.model_validate(
                {
                    "user_annotation": "<script>note</script>",
                    "user_explanation": "user reason",
                    "ai_explanation": "AI reason",
                }
            ),
        )
        await update_enrichment(
            engine, 1, EnrichmentUpdate.model_validate({"user_explanation": None})
        )
        first = await detail(engine, 1)
        assert first is not None
        assert first.enrichment.user_annotation == "<script>note</script>"
        assert first.enrichment.user_explanation is None
        assert first.enrichment.ai_explanation == "AI reason"
        await update_enrichment(
            engine,
            1,
            EnrichmentUpdate.model_validate(
                {"user_annotation": "changed", "ai_explanation": None}
            ),
        )
        first = await detail(engine, 1)
        assert first is not None
        assert first.enrichment.user_annotation == "changed"
        assert first.enrichment.ai_explanation is None
        await update_enrichment(
            engine, 1, EnrichmentUpdate.model_validate({"user_annotation": None})
        )
        first = await detail(engine, 1)
        assert first is not None
        assert first.enrichment.user_annotation is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["\ufeff", "🛒 groceries"])
async def test_unicode_category_survives_storage_and_detail(
    migrated_url: str, category: str
) -> None:
    engine = create_async_engine(migrated_url)
    try:
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
        patch = EnrichmentUpdate.model_validate(
            {"category": {"value": category, "status": "confirmed", "source": "user"}}
        )
        await update_enrichment(engine, 1, patch)
        result = await detail(engine, 1)
        assert result is not None
        assert result.enrichment.category.value == category
    finally:
        await engine.dispose()
