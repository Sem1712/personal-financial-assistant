import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.infrastructure.models import (
    TransactionClassification,
    TransactionObservation,
)
from personal_financial_assistant.rules import (
    CategoryOverride,
    GeneratedProposal,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
    confirm_preference,
    create_preference,
    propose_preference,
    set_override,
)
from personal_financial_assistant.rules.work import reapply_selected
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    detail,
    update_enrichment,
)


@pytest.mark.asyncio
async def test_selected_reapplication_preserves_overrides_and_unselected_occurrences(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) SELECT n, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed' FROM generate_series(1, 50) AS n",
                "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 50, 1)",
                "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) SELECT n, repeat('a',64), 0, n, 1, '2025-01-01', -100, 'EUR', 'shop', 'booked', repeat('b',64), n FROM generate_series(1, 50) AS n",
                "INSERT INTO occurrence_observation SELECT id, id FROM transaction_occurrence",
            ):
                await connection.execute(text(statement))
        preference = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "food", match_text="shop"
            ),
        )
        await confirm_preference(engine, preference.id, preference.revision)
        await propose_preference(
            engine,
            GeneratedProposal(
                PreferenceInput(
                    PreferenceKind.SUBSTRING_DESCRIPTION, "other", match_text="shop"
                ),
                ProposalOrigin.AI,
            ),
        )
        await set_override(engine, 1, "personal")
        await update_enrichment(
            engine, 1, EnrichmentUpdate.model_validate({"user_annotation": "preserved"})
        )
        summary = await reapply_selected(engine, (*range(1, 26), 999))
        assert summary.completed == 25
        assert summary.items[-1].status == "not_found"
        assert summary.items[0].result is not None
        assert summary.items[0].result.category == CategoryOverride("personal", 1)
        assert all(
            item.result is not None and len(item.result.blocked_ai_conflicts) == 1
            for item in summary.items[:-1]
        )
        record = await detail(engine, 1)
        assert record is not None and record.enrichment.user_annotation == "preserved"
        async with engine.connect() as connection:
            categories = (
                await connection.execute(
                    select(
                        TransactionClassification.occurrence_id,
                        TransactionClassification.value,
                    ).where(TransactionClassification.dimension == "category")
                )
            ).all()
            observations = (
                (await connection.execute(select(TransactionObservation.operation)))
                .scalars()
                .all()
            )
        assert dict(categories) == {
            1: "personal",
            **dict.fromkeys(range(2, 26), "food"),
        }
        assert observations == ["shop"] * 50
    finally:
        await engine.dispose()
