import asyncio

import pytest
from personal_financial_assistant.rules.proposals import propose_preference
from personal_financial_assistant.rules.review import (
    StaleReview,
    approve_application_conflict,
    preview_application_conflict,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules.categories import (
    confirm_merchant_default,
    confirm_preference,
    create_merchant_default,
    create_preference,
)
from personal_financial_assistant.rules.evaluation import evaluate_rules
from personal_financial_assistant.rules.merchants import (
    create_matching_entry,
    create_merchant,
)
from personal_financial_assistant.rules.overrides import set_override
from personal_financial_assistant.rules.types import (
    GeneratedProposal,
    MatchingEntryInput,
    MatchKind,
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
)
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    update_enrichment,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["new_rule", "override", "category", "evidence"])
async def test_review_snapshot_rejects_relevant_intervening_changes(
    migrated_url: str, change: str
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                (
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
                ),
                "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 2, 1)",
                (
                    "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, "
                    "transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) "
                    "VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', 'shop', "
                    "'booked', repeat('b',64), 1), "
                    "(2, repeat('a',64), 0, 2, 1, '2025-01-01', -100, 'EUR', 'shop extra', "
                    "'booked', repeat('b',64), 2)"
                ),
                "INSERT INTO occurrence_observation VALUES (1, 1)",
            ):
                await connection.execute(text(statement))
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "shop")
        )
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        await confirm_merchant_default(engine, default.id, default.revision)
        await propose_preference(
            engine,
            GeneratedProposal(
                PreferenceInput(
                    PreferenceKind.SUBSTRING_DESCRIPTION, "other", match_text="shop"
                ),
                ProposalOrigin.AI,
            ),
        )
        conflict = (await evaluate_rules(engine, 1)).blocked_ai_conflicts[0]
        preview = await preview_application_conflict(engine, conflict.conflict_id)

        if change == "new_rule":
            await create_preference(
                engine,
                PreferenceInput(
                    PreferenceKind.EXACT_DESCRIPTION, "new", match_text="shop"
                ),
            )
        elif change == "override":
            await set_override(engine, 1, "override")
        elif change == "category":
            await update_enrichment(
                engine,
                1,
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
        else:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "SELECT id FROM transaction_occurrence WHERE id = 1 FOR UPDATE"
                    )
                )
                await connection.execute(
                    text("INSERT INTO occurrence_observation VALUES (1, 2)")
                )
                await connection.execute(
                    text(
                        "UPDATE occurrence_evidence_revision SET revision = revision + 1 WHERE occurrence_id = 1"
                    )
                )

        with pytest.raises(StaleReview):
            await approve_application_conflict(
                engine, conflict.conflict_id, preview.snapshot_id
            )
        result = await evaluate_rules(engine, 1)
        assert any(
            block.conflict_id == conflict.conflict_id
            for block in result.blocked_ai_conflicts
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirmation_and_evaluation_serialize_under_configuration_lock(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                (
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
                ),
                "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 1, 1)",
                (
                    "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, "
                    "transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) "
                    "VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', 'shop', "
                    "'booked', repeat('b',64), 1)"
                ),
                "INSERT INTO occurrence_observation VALUES (1, 1)",
            ):
                await connection.execute(text(statement))
        user = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "food", match_text="shop"
            ),
        )
        await propose_preference(
            engine,
            GeneratedProposal(
                PreferenceInput(
                    PreferenceKind.SUBSTRING_DESCRIPTION, "other", match_text="shop"
                ),
                ProposalOrigin.AI,
            ),
        )
        await asyncio.gather(
            confirm_preference(engine, user.id, user.revision),
            evaluate_rules(engine, 1),
        )
        result = await evaluate_rules(engine, 1)
        assert len(result.blocked_ai_conflicts) == 1
        assert result.blocked_ai_conflicts[0].confirmed_entry == user.reference
    finally:
        await engine.dispose()
