import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules.categories import (
    confirm_merchant_default,
    confirm_preference,
    create_merchant_default,
    create_preference,
    inspect_merchant_default,
)
from personal_financial_assistant.rules.evaluation import evaluate_rules
from personal_financial_assistant.rules.merchants import (
    create_matching_entry,
    create_merchant,
)
from personal_financial_assistant.rules.overrides import set_override
from personal_financial_assistant.rules.proposals import (
    ChangeSuggestionRecord,
    propose_merchant_default_edit,
    propose_merchant_disable,
    propose_preference,
)
from personal_financial_assistant.rules.review import (
    StaleReview,
    approve_application_conflict,
    approve_change_suggestion,
    preview_application_conflict,
    preview_change_suggestion,
    reject_application_conflict,
)
from personal_financial_assistant.rules.types import (
    CategoryApplied,
    CategoryOverride,
    GeneratedProposal,
    MatchingEntryInput,
    MatchKind,
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
)


@pytest.mark.asyncio
async def test_twenty_ai_conflicts_are_scoped_and_reviewed(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                (
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) SELECT n, 1, '2025-01-01', -100, 'EUR', "
                    "'booked', 'confirmed' FROM generate_series(1, 21) AS n"
                ),
                "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 21, 1)",
                (
                    "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, "
                    "transaction_date, amount_minor, currency, operation, booking_status, candidate_key, occurrence_ordinal) "
                    "SELECT n, repeat('a',64), 0, n, 1, '2025-01-01', -100, 'EUR', "
                    "CASE WHEN n = 21 THEN 'other shop' ELSE 'shop' END, 'booked', repeat('b',64), n "
                    "FROM generate_series(1, 21) AS n"
                ),
                "INSERT INTO occurrence_observation SELECT id, id FROM transaction_occurrence",
            ):
                await connection.execute(text(statement))
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "shop")
        )
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        default = await confirm_merchant_default(engine, default.id, default.revision)
        forwarded = GeneratedProposal(
            value=PreferenceInput(
                PreferenceKind.SUBSTRING_DESCRIPTION, "other", match_text="shop"
            ),
            origin=ProposalOrigin.AI,
        ).transform(lambda value: value)
        ai = await propose_preference(engine, forwarded)
        assert ai.id == default.id
        assert ai.origin == "ai" and not ai.confirmed

        conflicts: list[int] = []
        for occurrence_id in range(1, 21):
            result = await evaluate_rules(engine, occurrence_id)
            assert result.category == CategoryApplied(
                value="food", winning_rules=(default.reference,), status="confirmed"
            )
            assert len(result.blocked_ai_conflicts) == 1
            blocked = result.blocked_ai_conflicts[0]
            assert blocked.ai_entry == ai.reference
            assert blocked.confirmed_entry == default.reference
            conflicts.append(blocked.conflict_id)
        nonconflicting = await evaluate_rules(engine, 21)
        assert not nonconflicting.blocked_ai_conflicts
        assert nonconflicting.category == CategoryApplied(
            value="other", winning_rules=(ai.reference,), status="provisional"
        )

        preview = await preview_application_conflict(engine, conflicts[0])
        await set_override(engine, 1, "personal")
        with pytest.raises(StaleReview):
            await approve_application_conflict(
                engine, conflicts[0], preview.snapshot_id
            )
        preview = await preview_application_conflict(engine, conflicts[0])
        await approve_application_conflict(engine, conflicts[0], preview.snapshot_id)
        approved = await evaluate_rules(engine, 1)
        assert approved.category == CategoryOverride(value="personal", occurrence_id=1)
        assert not approved.blocked_ai_conflicts
        still_blocked = await evaluate_rules(engine, 2)
        assert len(still_blocked.blocked_ai_conflicts) == 1

        preview = await preview_application_conflict(engine, conflicts[1])
        await reject_application_conflict(engine, conflicts[1], preview.snapshot_id)
        assert len((await evaluate_rules(engine, 2)).blocked_ai_conflicts) == 1

        another = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "different", match_text="shop"
            ),
        )
        await confirm_preference(engine, another.id, another.revision)
        multi = await evaluate_rules(engine, 3)
        assert len(multi.blocked_ai_conflicts) == 2
        preview = await preview_application_conflict(
            engine, multi.blocked_ai_conflicts[0].conflict_id
        )
        await approve_application_conflict(
            engine, multi.blocked_ai_conflicts[0].conflict_id, preview.snapshot_id
        )
        assert len((await evaluate_rules(engine, 3)).blocked_ai_conflicts) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ai_edits_and_indirect_disable_require_explicit_approval(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        default = await confirm_merchant_default(engine, default.id, default.revision)
        proposal = GeneratedProposal(
            value=MerchantDefaultInput(merchant.id, "other"), origin=ProposalOrigin.AI
        )
        suggestion = await propose_merchant_default_edit(
            engine, default.id, default.revision, proposal
        )
        assert isinstance(suggestion, ChangeSuggestionRecord)
        assert suggestion.state == "pending"
        assert await inspect_merchant_default(engine, default.id) == default
        preview = await preview_change_suggestion(engine, suggestion.id)
        await approve_change_suggestion(engine, suggestion.id, preview.snapshot_id)
        updated = await inspect_merchant_default(engine, default.id)
        assert updated.category == "other" and updated.confirmed

        disable = await propose_merchant_disable(
            engine,
            merchant.id,
            merchant.revision,
            GeneratedProposal(value=False, origin=ProposalOrigin.AI),
        )
        assert isinstance(disable, ChangeSuggestionRecord)
        assert disable.state == "pending"
        assert (await inspect_merchant_default(engine, default.id)).enabled
    finally:
        await engine.dispose()
