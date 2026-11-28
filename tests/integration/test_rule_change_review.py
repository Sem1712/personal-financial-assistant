import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.infrastructure.models import ChangeSuggestion
from personal_financial_assistant.rules.categories import (
    confirm_merchant_default,
    create_merchant_default,
    inspect_merchant_default,
)
from personal_financial_assistant.rules.merchants import (
    confirm_matching_entry,
    create_matching_entry,
    create_merchant,
    edit_merchant,
    inspect_merchant,
)
from personal_financial_assistant.rules.proposals import (
    ChangeSuggestionRecord,
    propose_merchant_default_edit,
    propose_merchant_disable,
)
from personal_financial_assistant.rules.review import (
    StaleReview,
    approve_change_suggestion,
    preview_change_suggestion,
    reject_change_suggestion,
)
from personal_financial_assistant.rules.storage import rules_transaction
from personal_financial_assistant.rules.types import (
    GeneratedProposal,
    MatchingEntryInput,
    MatchKind,
    MerchantDefaultInput,
    MerchantInput,
    ProposalOrigin,
)


@pytest.mark.asyncio
async def test_change_preview_and_approval_preserve_confirmed_rule_until_review(
    migrated_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        default = await confirm_merchant_default(engine, default.id, default.revision)
        suggestion = await propose_merchant_default_edit(
            engine,
            default.id,
            default.revision,
            GeneratedProposal(
                MerchantDefaultInput(merchant.id, "other"), ProposalOrigin.AI
            ),
        )
        assert isinstance(suggestion, ChangeSuggestionRecord)
        preview = await preview_change_suggestion(engine, suggestion.id)
        assert "food" not in repr(preview) and "other" not in repr(preview)
        assert preview.affected_confirmed == (default.reference,)
        assert preview.current["category"] == "food"
        assert preview.proposed["category"] == "other"
        assert await inspect_merchant_default(engine, default.id) == default
        await approve_change_suggestion(engine, suggestion.id, preview.snapshot_id)
        updated = await inspect_merchant_default(engine, default.id)
        assert updated.category == "other" and updated.confirmed
        assert updated.origin == "ai"
        assert "food" not in caplog.text and "other" not in caplog.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_merchant_preview_becomes_stale_after_affected_change(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        await confirm_merchant_default(engine, default.id, default.revision)
        suggestion = await propose_merchant_disable(
            engine,
            merchant.id,
            merchant.revision,
            GeneratedProposal(False, ProposalOrigin.AI),
        )
        assert isinstance(suggestion, ChangeSuggestionRecord)
        preview = await preview_change_suggestion(engine, suggestion.id)
        assert default.reference in preview.affected_confirmed
        await edit_merchant(
            engine, merchant.id, merchant.revision, MerchantInput("Renamed")
        )
        with pytest.raises(StaleReview):
            await approve_change_suggestion(engine, suggestion.id, preview.snapshot_id)
        assert (await inspect_merchant(engine, merchant.id)).enabled
        async with rules_transaction(engine) as session:
            assert (
                await session.scalar(
                    select(ChangeSuggestion.state).where(
                        ChangeSuggestion.id == suggestion.id
                    )
                )
                == "stale"
            )
        preview = await preview_change_suggestion(engine, suggestion.id)
        await reject_change_suggestion(engine, suggestion.id, preview.snapshot_id)
        assert (await inspect_merchant(engine, merchant.id)).enabled
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_new_confirmed_rule_invalidates_merchant_disable_preview(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        await confirm_merchant_default(engine, default.id, default.revision)
        suggestion = await propose_merchant_disable(
            engine,
            merchant.id,
            merchant.revision,
            GeneratedProposal(False, ProposalOrigin.AI),
        )
        assert isinstance(suggestion, ChangeSuggestionRecord)
        preview = await preview_change_suggestion(engine, suggestion.id)
        entry = await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "shop")
        )
        await confirm_matching_entry(engine, entry.id, entry.revision)
        with pytest.raises(StaleReview):
            await approve_change_suggestion(engine, suggestion.id, preview.snapshot_id)
        assert (await inspect_merchant(engine, merchant.id)).enabled
        fresh = await preview_change_suggestion(engine, suggestion.id)
        assert entry.reference in fresh.affected_confirmed
        await approve_change_suggestion(engine, suggestion.id, fresh.snapshot_id)
        assert not (await inspect_merchant(engine, merchant.id)).enabled
    finally:
        await engine.dispose()
