from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from personal_financial_assistant.rules.storage import (
    RulesCommitUnknown,
    commit_rules_transaction,
)
from personal_financial_assistant.rules.types import (
    CategoryApplied,
    EntryKind,
    EvaluationResult,
    GeneratedProposal,
    MerchantNoMatch,
    ProposalOrigin,
    RuleReference,
    normalize_description,
    validate_category,
    validate_rule_text,
)
from personal_financial_assistant.rules.work import EvaluationItem, EvaluationSummary


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("  CORNER\t  SHOP\n", "corner shop"),
        ("Straße", "strasse"),
        (" \t ", ""),
        ("A-B / C", "a-b / c"),
    ],
)
def test_normalization_preserves_non_whitespace_characters(
    text: str, normalized: str
) -> None:
    assert normalize_description(text) == normalized


@pytest.mark.parametrize(
    "text", ["", " \t\u00a0", "private\x00merchant", "private\ud800"]
)
def test_invalid_rule_text_has_sanitized_error(text: str) -> None:
    with pytest.raises(ValueError) as error:
        validate_rule_text(text)
    if text:
        assert text not in str(error.value)


def test_forwarded_and_transformed_ai_proposals_keep_generation_origin() -> None:
    proposal = GeneratedProposal(value="shop", origin=ProposalOrigin.AI)
    transformed = proposal.transform(str.upper)
    assert transformed.value == "SHOP"
    assert transformed.origin is ProposalOrigin.AI


def test_proposals_reject_unknown_generation_origin_without_leaking_value() -> None:
    with pytest.raises(ValueError) as error:
        GeneratedProposal.from_trusted("private merchant", "unknown")
    assert "private merchant" not in str(error.value)


def test_result_and_proposal_representations_hide_financial_payloads() -> None:
    secret = "sensitive synthetic category"
    proposal = GeneratedProposal(secret, ProposalOrigin.AI)
    result = EvaluationResult(
        1,
        1,
        MerchantNoMatch(),
        CategoryApplied(
            secret, (RuleReference(EntryKind.MERCHANT_DEFAULT, 1),), "provisional"
        ),
        (),
        (),
    )
    item = EvaluationItem(1, "completed", result)
    assert secret not in repr(proposal)
    assert secret not in repr(result)
    assert secret not in repr(
        EvaluationSummary(attempted=1, completed=1, items=(item,))
    )


@pytest.mark.parametrize(
    "category", ["", " \t\u00a0", "private\x00category", "a\ud800"]
)
def test_invalid_category_is_rejected_without_leaking_payload(category: str) -> None:
    with pytest.raises(ValueError) as error:
        validate_category(category)
    if category:
        assert category not in str(error.value)


def test_valid_category_is_not_normalized() -> None:
    assert validate_category("  Groceries  ") == "  Groceries  "


@pytest.mark.asyncio
async def test_commit_disconnect_requires_inspection_and_is_not_retried() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = OSError("private database detail")

    with pytest.raises(RulesCommitUnknown, match="read current state") as error:
        await commit_rules_transaction(session)

    assert "private database detail" not in str(error.value)
    session.commit.assert_awaited_once()
