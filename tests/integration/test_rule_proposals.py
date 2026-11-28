import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules.categories import (
    confirm_merchant_default,
    create_merchant_default,
    inspect_merchant_default,
    inspect_preference,
)
from personal_financial_assistant.rules.merchants import (
    confirm_matching_entry,
    create_merchant,
    inspect_matching_entry,
    inspect_merchant,
)
from personal_financial_assistant.rules.proposals import (
    ChangeSuggestionRecord,
    propose_matching_entry,
    propose_merchant_default_edit,
    propose_merchant_disable,
    propose_merchant_edit,
    propose_preference,
    propose_rule_change,
)
from personal_financial_assistant.rules.types import (
    GeneratedProposal,
    MatchingEntryInput,
    MatchKind,
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
    RuleValidationError,
)


@pytest.mark.asyncio
async def test_proposals_preserve_provenance_and_protect_confirmed_rules(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        confirmed = await confirm_merchant_default(engine, default.id, default.revision)
        pending = await propose_merchant_default_edit(
            engine,
            default.id,
            confirmed.revision,
            GeneratedProposal(
                MerchantDefaultInput(merchant.id, "travel"), ProposalOrigin.AI
            ).transform(lambda value: value),
        )
        assert isinstance(pending, ChangeSuggestionRecord)
        assert pending.state == "pending" and pending.origin == "ai"
        assert await inspect_merchant_default(engine, default.id) == confirmed
        pending_disable = await propose_merchant_disable(
            engine,
            merchant.id,
            merchant.revision,
            GeneratedProposal(False, ProposalOrigin.AI),
        )
        assert isinstance(pending_disable, ChangeSuggestionRecord)
        assert pending_disable.state == "pending"
        assert (await inspect_merchant(engine, merchant.id)).enabled
        pending_rename = await propose_merchant_edit(
            engine,
            merchant.id,
            merchant.revision,
            GeneratedProposal(MerchantInput("Other"), ProposalOrigin.AI),
        )
        assert isinstance(pending_rename, ChangeSuggestionRecord)
        assert (await inspect_merchant(engine, merchant.id)).canonical_name == "Shop"
        with pytest.raises(RuleValidationError):
            await propose_merchant_default_edit(
                engine,
                default.id,
                confirmed.revision,
                GeneratedProposal(
                    MerchantDefaultInput(merchant.id, "travel"), ProposalOrigin.SERVICE
                ),
            )
        ai = await propose_preference(
            engine,
            GeneratedProposal(
                PreferenceInput(
                    PreferenceKind.EXACT_DESCRIPTION, "food", match_text="shop"
                ),
                ProposalOrigin.AI,
            ),
        )
        match = await propose_matching_entry(
            engine,
            GeneratedProposal(
                MatchingEntryInput(merchant.id, MatchKind.ALIAS, "shop"),
                ProposalOrigin.AI,
            ),
        )
        confirmed_match = await confirm_matching_entry(engine, match.id, match.revision)
        change = await propose_rule_change(
            engine,
            match.reference,
            confirmed_match.revision,
            GeneratedProposal(
                MatchingEntryInput(merchant.id, MatchKind.ALIAS, "different"),
                ProposalOrigin.AI,
            ),
        )
        assert isinstance(change, ChangeSuggestionRecord) and change.state == "pending"
        assert await inspect_matching_entry(engine, match.id) == confirmed_match
        disable = await propose_rule_change(
            engine,
            match.reference,
            confirmed_match.revision,
            GeneratedProposal(None, ProposalOrigin.AI),
        )
        assert (
            isinstance(disable, ChangeSuggestionRecord) and disable.state == "pending"
        )
        saved = await inspect_preference(engine, ai.id)
        assert saved.origin == "ai" and not saved.confirmed
        with pytest.raises(RuleValidationError):
            await propose_preference(
                engine,
                GeneratedProposal(
                    PreferenceInput(
                        PreferenceKind.EXACT_DESCRIPTION, "x", match_text="shop"
                    ),
                    ProposalOrigin.USER,
                ),
            )
    finally:
        await engine.dispose()
