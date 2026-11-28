import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.infrastructure.models import (
    ApplicationApproval,
    ApplicationConflict,
)
from personal_financial_assistant.rules.conflicts import (
    ConflictCandidate,
    detect_application_conflicts,
)
from personal_financial_assistant.rules.storage import rules_transaction
from personal_financial_assistant.rules.types import (
    EntryKind,
    ProposalOrigin,
    RuleReference,
)


@pytest.mark.asyncio
async def test_conflicts_persist_rejections_and_scope_approval(
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
                "INSERT INTO merchant (id, canonical_name) VALUES (1, 'shop')",
                "INSERT INTO merchant_default (id, merchant_id, category, origin, confirmed) VALUES (1, 1, 'food', 'user', true)",
                (
                    "INSERT INTO classification_preference (id, match_kind, match_text, category, origin) "
                    "VALUES (1, 'exact_description', 'shop', 'other', 'ai')"
                ),
            ):
                await connection.execute(text(statement))
        ai = ConflictCandidate(
            RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, 1),
            1,
            ProposalOrigin.AI,
            False,
            "other",
            (),
        )
        confirmed = ConflictCandidate(
            RuleReference(EntryKind.MERCHANT_DEFAULT, 1),
            1,
            ProposalOrigin.USER,
            True,
            "food",
            (1,),
        )
        async with rules_transaction(engine, occurrence_id=1) as session:
            result = await detect_application_conflicts(
                session, 1, 1, "category", [ai, confirmed]
            )
            assert result.eligible == (confirmed,)
            assert len(result.blocked) == 1
            conflict_id = result.blocked[0].conflict_id
        async with rules_transaction(engine, occurrence_id=1) as session:
            conflict = await session.get(ApplicationConflict, conflict_id)
            assert conflict is not None
            conflict.state = "rejected"
        async with rules_transaction(engine, occurrence_id=1) as session:
            result = await detect_application_conflicts(
                session, 1, 1, "category", [ai, confirmed]
            )
            assert result.blocked[0].conflict_id == conflict_id
            assert (
                await session.scalar(select(ApplicationConflict.state))
            ) == "rejected"
            conflict = await session.get(ApplicationConflict, conflict_id)
            assert conflict is not None
            conflict.state = "approved"
            session.add(
                ApplicationApproval(
                    conflict_id=conflict_id,
                    ai_revision=1,
                    confirmed_revision=1,
                    evidence_revision=1,
                    merchant_revisions=[[1, 1]],
                )
            )
        async with rules_transaction(engine, occurrence_id=1) as session:
            result = await detect_application_conflicts(
                session, 1, 1, "category", [ai, confirmed]
            )
            assert not result.blocked
            assert result.eligible == (ai, confirmed)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE merchant SET enabled_revision = 2 WHERE id = 1")
            )
        async with rules_transaction(engine, occurrence_id=1) as session:
            result = await detect_application_conflicts(
                session, 1, 1, "category", [ai, confirmed]
            )
            assert result.blocked[0].conflict_id == conflict_id
            assert (await session.scalar(select(ApplicationConflict.state))) == "stale"
    finally:
        await engine.dispose()
