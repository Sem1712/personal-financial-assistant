from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from personal_financial_assistant.infrastructure.models import ClassificationPreference
from personal_financial_assistant.rules import categories
from personal_financial_assistant.rules.categories import (
    CategoryCandidate,
    confirm_preference,
    select_category,
)
from personal_financial_assistant.rules.conflicts import (
    ApprovalScope,
    application_is_approved,
)
from personal_financial_assistant.rules.review import review_snapshot_is_current
from personal_financial_assistant.rules.types import (
    CategoryApplied,
    EntryKind,
    GeneratedProposal,
    PreferenceKind,
    ProposalOrigin,
    RuleReference,
)


def test_approval_is_specific_to_typed_pair_and_reviewed_revisions() -> None:
    ai = RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, 1)
    confirmed = RuleReference(EntryKind.MERCHANT_DEFAULT, 1)
    scope = ApprovalScope(ai, 1, confirmed, 2, 3, ((5, 1),))
    assert application_is_approved("approved", scope, scope)
    assert not application_is_approved("rejected", scope, scope)
    assert not application_is_approved(
        "approved", scope, ApprovalScope(ai, 2, confirmed, 2, 3, ((5, 1),))
    )
    assert not application_is_approved(
        "approved", scope, ApprovalScope(ai, 1, confirmed, 2, 4, ((5, 1),))
    )
    assert not application_is_approved(
        "approved", scope, ApprovalScope(ai, 1, confirmed, 2, 3, ((5, 2),))
    )
    assert not application_is_approved(
        "approved", scope, ApprovalScope(confirmed, 1, ai, 2, 3, ((5, 1),))
    )


def test_approved_candidate_still_obeys_normal_precedence() -> None:
    confirmed = CategoryCandidate(
        RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, 1),
        "confirmed",
        PreferenceKind.EXACT_DESCRIPTION,
        True,
    )
    ai = CategoryCandidate(
        RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, 2),
        "suggested",
        PreferenceKind.SUBSTRING_DESCRIPTION,
        False,
    )
    selection = select_category(1, None, [confirmed, ai])
    assert selection.decision == CategoryApplied(
        value="confirmed", winning_rules=(confirmed.reference,), status="confirmed"
    )


def test_provenance_cannot_be_lost_by_forwarding_or_unknown_origin() -> None:
    forwarded = GeneratedProposal(value="shop", origin=ProposalOrigin.AI).transform(
        str.upper
    )
    assert forwarded.origin is ProposalOrigin.AI
    with pytest.raises(ValueError):
        GeneratedProposal.from_trusted("shop", "unknown")


@pytest.mark.parametrize("changed", ["candidates", "override", "category", "evidence"])
def test_review_snapshot_rejects_all_changed_inputs(changed: str) -> None:
    reviewed: dict[str, object] = {
        "candidates": [{"kind": "merchant_default", "id": 1, "revision": 1}],
        "override": None,
        "category": {"value": "food", "source": "user"},
        "evidence": 1,
    }
    current = dict(reviewed)
    current[changed] = "changed"
    assert review_snapshot_is_current(reviewed, reviewed)
    assert not review_snapshot_is_current(reviewed, current)


@pytest.mark.asyncio
async def test_user_confirmation_preserves_ai_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = ClassificationPreference(
        id=1,
        match_kind="exact_description",
        match_text="shop",
        category="food",
        origin="ai",
        confirmed=False,
        enabled=True,
        revision=1,
    )
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = row

    @asynccontextmanager
    async def transaction(_bind: object) -> AsyncGenerator[AsyncSession]:
        yield session

    monkeypatch.setattr(categories, "rules_transaction", transaction)
    result = await confirm_preference(AsyncMock(), 1, 1)
    assert result.confirmed and result.origin == "ai"
