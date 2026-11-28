import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules import (
    CategoryApplied,
    CategoryOverride,
    CategoryUnchanged,
    MatchingEntryInput,
    MatchKind,
    MerchantConflict,
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    RuleValidationError,
    clear_override,
    confirm_merchant_default,
    confirm_preference,
    create_matching_entry,
    create_merchant,
    create_merchant_default,
    create_preference,
    evaluate_rules,
    inspect_override,
    set_override,
    set_preference_enabled,
)
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    OccurrenceNotFound,
    update_enrichment,
)
from personal_financial_assistant.transactions.service import detail


@pytest.mark.asyncio
async def test_default_preference_override_and_reapplication(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                (
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) VALUES "
                    "(1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed'), "
                    "(2, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
                ),
                "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 1, 1)",
                (
                    "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, "
                    "transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) "
                    "VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', "
                    "'SHOP', 'booked', repeat('b',64), 1)"
                ),
                "INSERT INTO occurrence_observation VALUES (1, 1)",
            ):
                await connection.execute(text(statement))
        await update_enrichment(
            engine,
            1,
            EnrichmentUpdate.model_validate(
                {
                    "transaction_type": {
                        "value": "expense",
                        "status": "confirmed",
                        "source": "user",
                    },
                    "user_annotation": "preserve",
                }
            ),
        )
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "shop")
        )
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        default = await confirm_merchant_default(engine, default.id, default.revision)
        default_result = await evaluate_rules(engine, 1)
        assert default_result.category == CategoryApplied(
            value="food", winning_rules=(default.reference,), status="confirmed"
        )

        preference = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "travel", match_text="shop"
            ),
        )
        preference = await confirm_preference(
            engine, preference.id, preference.revision
        )
        preferred = await evaluate_rules(engine, 1)
        assert preferred.category == CategoryApplied(
            value="travel", winning_rules=(preference.reference,), status="confirmed"
        )
        first_override = await set_override(engine, 1, "initial")
        changed_override = await set_override(engine, 1, "personal")
        assert changed_override.revision == first_override.revision + 1
        override = await inspect_override(engine, 1)
        assert override is not None and override.category == "personal"
        await update_enrichment(
            engine,
            1,
            EnrichmentUpdate.model_validate(
                {
                    "category": {
                        "value": "other",
                        "status": "provisional",
                        "source": "ai",
                    }
                }
            ),
        )
        overridden = await evaluate_rules(engine, 1)
        assert overridden.category == CategoryOverride(
            value="personal", occurrence_id=1
        )
        current = await detail(engine, 1)
        assert current is not None
        assert current.enrichment.category.value == "personal"
        assert current.enrichment.category.source == "user"
        assert current.enrichment.category.status == "confirmed"
        assert current.enrichment.category.confidence is None
        assert current.enrichment.transaction_type.value == "expense"
        assert current.enrichment.user_annotation == "preserve"

        await clear_override(engine, 1)
        current = await detail(engine, 1)
        assert current is not None and current.enrichment.category.value == "personal"
        assert (await evaluate_rules(engine, 1)).category == preferred.category
        second = await evaluate_rules(engine, 2)
        assert second.category == CategoryUnchanged(reason="no_rule")
        second_detail = await detail(engine, 2)
        assert second_detail is not None
        assert second_detail.enrichment.category.status == "unclassified"
        with pytest.raises(RuleValidationError):
            await set_override(engine, 1, " \t")
        with pytest.raises(OccurrenceNotFound):
            await set_override(engine, 999, "food")

        conflicting = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "other", match_text="shop"
            ),
        )
        conflicting = await confirm_preference(
            engine, conflicting.id, conflicting.revision
        )
        conflict_result = await evaluate_rules(engine, 1)
        assert conflict_result.category == CategoryUnchanged(reason="conflict")
        assert set(conflict_result.category_conflict_candidates) == {
            preference.reference,
            conflicting.reference,
        }
        current = await detail(engine, 1)
        assert current is not None and current.enrichment.category.value == "travel"

        await set_preference_enabled(
            engine, conflicting.id, conflicting.revision, False
        )
        other_merchant = await create_merchant(engine, MerchantInput("Other shop"))
        await create_matching_entry(
            engine, MatchingEntryInput(other_merchant.id, MatchKind.ALIAS, "shop")
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO classification_preference (match_kind, match_text, category, origin) "
                    "VALUES ('exact_description', 'shop', 'unreviewed', 'ai')"
                )
            )
        ambiguous = await evaluate_rules(engine, 1)
        assert isinstance(ambiguous.merchant, MerchantConflict)
        assert ambiguous.category == preferred.category
    finally:
        await engine.dispose()
