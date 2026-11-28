import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.rules.merchants import (
    confirm_matching_entry,
    create_matching_entry,
    create_merchant,
    edit_matching_entry,
    edit_merchant,
    inspect_matching_entry,
    inspect_merchant,
    set_matching_entry_enabled,
    set_merchant_enabled,
)
from personal_financial_assistant.rules.types import (
    MatchingEntryInput,
    MatchKind,
    MerchantInput,
    RuleNotFound,
    RuleValidationError,
    StaleRuleRevision,
)


@pytest.mark.asyncio
async def test_user_merchant_lifecycle_and_revision_checks(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        merchant = await create_merchant(engine, MerchantInput("Corner"))
        match = await create_matching_entry(
            engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "Straße Shop")
        )
        assert not match.confirmed
        assert match.normalized_text == "strasse shop"
        with pytest.raises(RuleValidationError):
            await create_matching_entry(
                engine, MatchingEntryInput(merchant.id, MatchKind.ALIAS, "STRASSE SHOP")
            )
        confirmed = await confirm_matching_entry(engine, match.id, match.revision)
        assert confirmed.confirmed and confirmed.origin == "user"
        with pytest.raises(StaleRuleRevision):
            await edit_matching_entry(
                engine,
                match.id,
                match.revision,
                MatchingEntryInput(merchant.id, MatchKind.ALIAS, "replacement"),
            )
        edited = await edit_matching_entry(
            engine,
            match.id,
            confirmed.revision,
            MatchingEntryInput(merchant.id, MatchKind.SUBSTRING, "Shop"),
        )
        assert edited.confirmed
        disabled = await set_matching_entry_enabled(
            engine, edited.id, edited.revision, False
        )
        assert not disabled.enabled
        assert await inspect_matching_entry(engine, edited.id) == disabled
        renamed = await edit_merchant(
            engine, merchant.id, merchant.revision, MerchantInput("New corner")
        )
        disabled_merchant = await set_merchant_enabled(
            engine, merchant.id, renamed.revision, False
        )
        assert await inspect_merchant(engine, merchant.id) == disabled_merchant
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT enabled_revision FROM merchant WHERE id = :id"),
                    {"id": merchant.id},
                )
                == 2
            )
        with pytest.raises(RuleNotFound):
            await inspect_merchant(engine, 999)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_explicit_confirmation_preserves_ai_origin(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO merchant (id, canonical_name) VALUES (1, 'synthetic')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO merchant_match (id, merchant_id, kind, original_text, normalized_text, origin) "
                    "VALUES (1, 1, 'alias', 'SHOP', 'shop', 'ai')"
                )
            )
        confirmed = await confirm_matching_entry(engine, 1, 1)
        assert confirmed.confirmed
        assert confirmed.origin == "ai"
    finally:
        await engine.dispose()
