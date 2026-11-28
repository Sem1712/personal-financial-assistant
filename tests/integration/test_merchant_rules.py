import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules import (
    MatchingEntryInput,
    MatchKind,
    MerchantConflict,
    MerchantInput,
    MerchantNoMatch,
    MerchantResolved,
    RuleValidationError,
    StaleRuleRevision,
    confirm_matching_entry,
    create_matching_entry,
    create_merchant,
    edit_matching_entry,
    edit_merchant,
    identify_merchant,
    inspect_matching_entry,
    inspect_merchant,
    set_matching_entry_enabled,
    set_merchant_enabled,
)


@pytest.mark.asyncio
async def test_merchant_management_and_identification_preserve_observations(
    migrated_url: str,
    caplog: pytest.LogCaptureFixture,
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
                    "transaction_date, amount_minor, currency, operation, details, booking_status, category, candidate_key, occurrence_ordinal) "
                    "VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', "
                    "' Card Payment ', 'STRASSE SHOP', 'booked', 'bank category', repeat('b',64), 1)"
                ),
                "INSERT INTO occurrence_observation VALUES (1, 1)",
            ):
                await connection.execute(text(statement))

        merchant = await create_merchant(engine, MerchantInput("Corner shop"))
        match = await create_matching_entry(
            engine,
            MatchingEntryInput(merchant.id, MatchKind.ALIAS, "Straße Shop"),
        )
        confirmed = await confirm_matching_entry(engine, match.id, match.revision)
        assert confirmed.confirmed
        assert confirmed.origin == "user"
        assert confirmed.revision == match.revision + 1
        with pytest.raises(StaleRuleRevision):
            await confirm_matching_entry(engine, match.id, match.revision)

        result = await identify_merchant(engine, 1)
        assert "STRASSE SHOP" not in repr(result)
        assert "STRASSE SHOP" not in caplog.text
        assert isinstance(result, MerchantResolved)
        assert result.merchant_id == merchant.id
        assert result.winning_entries == (match.reference,)
        inspected = await inspect_merchant(engine, merchant.id)
        assert inspected.canonical_name == "Corner shop"
        renamed = await edit_merchant(
            engine, merchant.id, merchant.revision, MerchantInput("Corner Store")
        )
        assert renamed.canonical_name == "Corner Store"
        edited = await edit_matching_entry(
            engine,
            match.id,
            confirmed.revision,
            MatchingEntryInput(merchant.id, MatchKind.ALIAS, "STRASSE SHOP"),
        )
        assert (await inspect_matching_entry(engine, match.id)) == edited
        disabled = await set_matching_entry_enabled(
            engine, match.id, edited.revision, False
        )
        assert await identify_merchant(engine, 1) == MerchantNoMatch()
        enabled = await set_matching_entry_enabled(
            engine, match.id, disabled.revision, True
        )
        assert enabled.confirmed

        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT operation, details, category FROM transaction_observation WHERE id = 1"
                    )
                )
            ).one()
            assert tuple(row) == (" Card Payment ", "STRASSE SHOP", "bank category")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_merchants_duplicates_and_conflicts(migrated_url: str) -> None:
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
                    "transaction_date, amount_minor, currency, details, booking_status, candidate_key, occurrence_ordinal) "
                    "VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', "
                    "'shop terminal', 'booked', repeat('b',64), 1)"
                ),
                "INSERT INTO occurrence_observation VALUES (1, 1)",
            ):
                await connection.execute(text(statement))

        first = await create_merchant(engine, MerchantInput("First"))
        second = await create_merchant(engine, MerchantInput("Second"))
        first_match = await create_matching_entry(
            engine, MatchingEntryInput(first.id, MatchKind.SUBSTRING, "SHOP")
        )
        with pytest.raises(RuleValidationError):
            await create_matching_entry(
                engine, MatchingEntryInput(first.id, MatchKind.SUBSTRING, " shop ")
            )
        second_match = await create_matching_entry(
            engine, MatchingEntryInput(second.id, MatchKind.SUBSTRING, "shop")
        )
        assert await identify_merchant(engine, 1) == MerchantConflict(
            candidates=(first_match.reference, second_match.reference)
        )
        first = await set_merchant_enabled(engine, first.id, first.revision, False)
        assert await identify_merchant(engine, 1) == MerchantResolved(
            merchant_id=second.id, winning_entries=(second_match.reference,)
        )
        second = await set_merchant_enabled(engine, second.id, second.revision, False)
        assert await identify_merchant(engine, 1) == MerchantNoMatch()
    finally:
        await engine.dispose()
