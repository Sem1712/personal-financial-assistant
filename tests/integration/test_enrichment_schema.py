import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_enrichment_constraints(migrated_url: str) -> None:
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
            await conn.execute(
                text(
                    "INSERT INTO transaction_classification (occurrence_id, dimension, value, status, source, confidence) VALUES (1, 'category', 'groceries', 'provisional', 'ai', 99.99)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO transaction_context (occurrence_id, user_annotation) VALUES (1, 'note')"
                )
            )
        invalid = (
            "INSERT INTO transaction_classification VALUES (1, 'category', 'food', 'confirmed', 'user', NULL)",
            "INSERT INTO transaction_classification VALUES (2, 'category', 'food', 'confirmed', 'user', NULL)",
            "INSERT INTO transaction_classification VALUES (1, 'transaction_type', 'invalid', 'confirmed', 'user', NULL)",
            "INSERT INTO transaction_classification VALUES (1, 'budget_treatment', 'ordinary', 'invalid', 'user', NULL)",
            "INSERT INTO transaction_classification VALUES (1, 'budget_treatment', 'ordinary', 'confirmed', 'bad', NULL)",
            "INSERT INTO transaction_classification VALUES (1, 'budget_treatment', 'ordinary', 'confirmed', 'user', 100.01)",
            "INSERT INTO transaction_classification VALUES (1, 'budget_treatment', 'ordinary', 'confirmed', 'user', 1.234)",
            "INSERT INTO transaction_context (occurrence_id) VALUES (1)",
            "DELETE FROM transaction_occurrence WHERE id = 1",
        )
        for statement in invalid:
            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.execute(text(statement))
        whitespace = [chr(code) for code in range(0x110000) if chr(code).isspace()]
        for value in (*whitespace, " \t"):
            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE transaction_classification SET value = :value WHERE occurrence_id = 1 AND dimension = 'category'"
                        ),
                        {"value": value},
                    )
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE transaction_classification SET value = :value WHERE occurrence_id = 1 AND dimension = 'category'"
                ),
                {"value": "\ufeff"},
            )
    finally:
        await engine.dispose()
