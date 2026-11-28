import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules.categories import (
    confirm_merchant_default,
    confirm_preference,
    create_merchant_default,
    create_preference,
    edit_merchant_default,
    edit_preference,
    inspect_merchant_default,
    inspect_preference,
    set_merchant_default_enabled,
    set_preference_enabled,
)
from personal_financial_assistant.rules.merchants import create_merchant
from personal_financial_assistant.rules.types import (
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
    PreferenceKind,
    RuleValidationError,
    StaleRuleRevision,
)


@pytest.mark.asyncio
async def test_user_category_rule_lifecycle(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Shop"))
        default = await create_merchant_default(
            engine, MerchantDefaultInput(merchant.id, "food")
        )
        assert not default.confirmed
        disabled = await set_merchant_default_enabled(
            engine, default.id, default.revision, False
        )
        with pytest.raises(RuleValidationError):
            await create_merchant_default(
                engine, MerchantDefaultInput(merchant.id, "other")
            )
        edited = await edit_merchant_default(
            engine,
            default.id,
            disabled.revision,
            MerchantDefaultInput(merchant.id, "travel"),
        )
        confirmed = await confirm_merchant_default(engine, edited.id, edited.revision)
        assert confirmed.confirmed and confirmed.origin == "user"
        assert not confirmed.enabled
        assert await inspect_merchant_default(engine, confirmed.id) == confirmed
        with pytest.raises(StaleRuleRevision):
            await confirm_merchant_default(engine, confirmed.id, edited.revision)
        reenabled = await set_merchant_default_enabled(
            engine, confirmed.id, confirmed.revision, True
        )
        assert reenabled.enabled and reenabled.category == "travel"

        preference = await create_preference(
            engine,
            PreferenceInput(
                PreferenceKind.EXACT_DESCRIPTION, "food", match_text=" SHOP "
            ),
        )
        assert preference.match_text == "shop"
        preference = await confirm_preference(
            engine, preference.id, preference.revision
        )
        changed = await edit_preference(
            engine,
            preference.id,
            preference.revision,
            PreferenceInput(PreferenceKind.MERCHANT, "other", merchant_id=merchant.id),
        )
        assert changed.confirmed and changed.match_text is None
        disabled_preference = await set_preference_enabled(
            engine, changed.id, changed.revision, False
        )
        assert await inspect_preference(engine, changed.id) == disabled_preference
        with pytest.raises(StaleRuleRevision):
            await edit_preference(
                engine,
                changed.id,
                changed.revision,
                PreferenceInput(
                    PreferenceKind.MERCHANT, "stale", merchant_id=merchant.id
                ),
            )
    finally:
        await engine.dispose()
