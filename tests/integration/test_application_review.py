import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from personal_financial_assistant.rules import (
    CategoryApplied,
    GeneratedProposal,
    MatchingEntryInput,
    MatchKind,
    MerchantDefaultInput,
    MerchantInput,
    MerchantResolved,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
    StaleReview,
    approve_application_conflict,
    confirm_matching_entry,
    confirm_merchant_default,
    confirm_preference,
    create_matching_entry,
    create_merchant,
    create_merchant_default,
    create_preference,
    edit_merchant_default,
    evaluate_rules,
    inspect_application_conflict,
    list_application_conflicts,
    preview_application_conflict,
    propose_matching_entry,
    propose_preference,
    reject_application_conflict,
    set_merchant_enabled,
)
from personal_financial_assistant.rules.application import prepare_application
from personal_financial_assistant.rules.storage import rules_transaction


async def _seed_occurrence(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        for statement in (
            "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
            "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')",
            "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 1, 1)",
            "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-01', -100, 'EUR', 'shop', 'booked', repeat('b',64), 1)",
            "INSERT INTO occurrence_observation VALUES (1, 1)",
        ):
            await connection.execute(text(statement))


@pytest.mark.asyncio
async def test_application_review_is_pair_scoped_and_rejection_persists(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await _seed_occurrence(engine)
        confirmed = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "food", match_text="shop"
            ),
        )
        await confirm_preference(engine, confirmed.id, confirmed.revision)
        ai = await propose_preference(
            engine,
            GeneratedProposal(
                PreferenceInput(
                    PreferenceKind.SUBSTRING_DESCRIPTION, "other", match_text="shop"
                ),
                ProposalOrigin.AI,
            ),
        )
        async with rules_transaction(engine, occurrence_id=1) as session:
            result = await prepare_application(session, 1)
            assert len(result.result.blocked_ai_conflicts) == 1
            conflict_id = result.result.blocked_ai_conflicts[0].conflict_id
        assert (await list_application_conflicts(engine))[0].id == conflict_id
        preview = await preview_application_conflict(engine, conflict_id)
        assert preview.conflict.ai_entry == ai.reference
        assert preview.result.category == CategoryApplied(
            value="food", winning_rules=(confirmed.reference,), status="confirmed"
        )
        await reject_application_conflict(engine, conflict_id, preview.snapshot_id)
        assert (
            await inspect_application_conflict(engine, conflict_id)
        ).state == "rejected"
        async with rules_transaction(engine, occurrence_id=1) as session:
            assert (
                len((await prepare_application(session, 1)).result.blocked_ai_conflicts)
                == 1
            )

        preview = await preview_application_conflict(engine, conflict_id)
        another = await create_preference(
            engine,
            PreferenceInput(PreferenceKind.EXACT_DESCRIPTION, "new", match_text="shop"),
        )
        with pytest.raises(StaleReview):
            await approve_application_conflict(engine, conflict_id, preview.snapshot_id)
        assert (
            await inspect_application_conflict(engine, conflict_id)
        ).state == "stale"
        preview = await preview_application_conflict(engine, conflict_id)
        await approve_application_conflict(engine, conflict_id, preview.snapshot_id)
        assert (
            await inspect_application_conflict(engine, conflict_id)
        ).state == "approved"
        async with rules_transaction(engine, occurrence_id=1) as session:
            final = await prepare_application(session, 1)
            assert not final.result.blocked_ai_conflicts
            assert final.result.category == CategoryApplied(
                value="food", winning_rules=(confirmed.reference,), status="confirmed"
            )
        assert another.id != confirmed.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_merchant_approval_obeys_precedence_and_enablement_revision(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await _seed_occurrence(engine)
        user_merchant = await create_merchant(engine, MerchantInput("Confirmed"))
        ai_merchant = await create_merchant(engine, MerchantInput("Suggested"))
        user_entry = await create_matching_entry(
            engine, MatchingEntryInput(user_merchant.id, MatchKind.ALIAS, "shop")
        )
        await confirm_matching_entry(engine, user_entry.id, user_entry.revision)
        ai_entry = await propose_matching_entry(
            engine,
            GeneratedProposal(
                MatchingEntryInput(ai_merchant.id, MatchKind.SUBSTRING, "shop"),
                ProposalOrigin.AI,
            ),
        )
        initial = await evaluate_rules(engine, 1)
        assert initial.merchant == MerchantResolved(
            user_merchant.id, (user_entry.reference,)
        )
        assert initial.blocked_ai_conflicts[0].ai_entry == ai_entry.reference
        conflict_id = initial.blocked_ai_conflicts[0].conflict_id
        preview = await preview_application_conflict(engine, conflict_id)
        assert preview.result.merchant == initial.merchant
        await approve_application_conflict(engine, conflict_id, preview.snapshot_id)
        approved = await evaluate_rules(engine, 1)
        assert approved.merchant == initial.merchant
        assert not approved.blocked_ai_conflicts
        ai_merchant = await set_merchant_enabled(
            engine, ai_merchant.id, ai_merchant.revision, False
        )
        await set_merchant_enabled(engine, ai_merchant.id, ai_merchant.revision, True)
        assert (await evaluate_rules(engine, 1)).blocked_ai_conflicts[
            0
        ].conflict_id == conflict_id
        assert (
            await inspect_application_conflict(engine, conflict_id)
        ).state == "stale"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_merchant_review_captures_current_and_hypothetical_categories(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await _seed_occurrence(engine)
        current_merchant = await create_merchant(engine, MerchantInput("Current"))
        suggested_merchant = await create_merchant(engine, MerchantInput("Suggested"))
        matching = await create_matching_entry(
            engine, MatchingEntryInput(current_merchant.id, MatchKind.SUBSTRING, "shop")
        )
        await confirm_matching_entry(engine, matching.id, matching.revision)
        default = await create_merchant_default(
            engine, MerchantDefaultInput(current_merchant.id, "food")
        )
        default = await confirm_merchant_default(engine, default.id, default.revision)
        await propose_matching_entry(
            engine,
            GeneratedProposal(
                MatchingEntryInput(suggested_merchant.id, MatchKind.ALIAS, "shop"),
                ProposalOrigin.AI,
            ),
        )
        conflict = (await evaluate_rules(engine, 1)).blocked_ai_conflicts[0]
        preview = await preview_application_conflict(engine, conflict.conflict_id)
        assert isinstance(preview.result.merchant, MerchantResolved)
        assert preview.result.merchant.merchant_id == suggested_merchant.id
        await edit_merchant_default(
            engine,
            default.id,
            default.revision,
            MerchantDefaultInput(current_merchant.id, "travel"),
        )
        with pytest.raises(StaleReview):
            await approve_application_conflict(
                engine, conflict.conflict_id, preview.snapshot_id
            )
    finally:
        await engine.dispose()
