import pytest

from personal_financial_assistant.rules.types import (
    EntryKind,
    GeneratedProposal,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
    RuleReference,
    validate_category,
    validate_rule_text,
)


def test_rule_reference_distinguishes_kinds_with_same_id() -> None:
    default = RuleReference(EntryKind.MERCHANT_DEFAULT, 1)
    preference = RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, 1)
    assert default != preference
    assert len({default, preference}) == 2


@pytest.mark.parametrize("entry_id", [0, -1, True])
def test_rule_reference_rejects_nonpositive_or_boolean_ids(entry_id: int) -> None:
    with pytest.raises(ValueError):
        RuleReference(EntryKind.MATCHING_ENTRY, entry_id)


def test_forwarded_proposal_retains_ai_origin_for_multiple_transforms() -> None:
    proposal = GeneratedProposal(value="shop", origin=ProposalOrigin.AI)
    forwarded = proposal.transform(str.upper).transform(lambda value: value + "!")
    assert forwarded.value == "SHOP!"
    assert forwarded.origin is ProposalOrigin.AI


def test_unknown_trusted_provenance_is_rejected_without_input_values() -> None:
    with pytest.raises(ValueError) as error:
        GeneratedProposal.from_trusted("private merchant", "private origin")
    assert "private merchant" not in str(error.value)
    assert "private origin" not in str(error.value)


@pytest.mark.parametrize("value", ["", "\u00a0 \t", "private\x00text", "a\ud800"])
def test_invalid_text_and_categories_do_not_expose_input(value: str) -> None:
    for validate in (validate_category, validate_rule_text):
        with pytest.raises(ValueError) as error:
            validate(value)
        if value:
            assert value not in str(error.value)


def test_category_preserves_original_value() -> None:
    assert validate_category("  Groceries  ") == "  Groceries  "


def test_preference_requires_exactly_its_matching_operand() -> None:
    preference = PreferenceInput(
        kind=PreferenceKind.EXACT_DESCRIPTION, category="food", match_text=" Shop "
    )
    assert preference.match_text == " Shop "
    with pytest.raises(ValueError):
        PreferenceInput(
            kind=PreferenceKind.MERCHANT,
            category="food",
            merchant_id=1,
            match_text="Shop",
        )
    with pytest.raises(ValueError):
        PreferenceInput(kind=PreferenceKind.MERCHANT, category="food")
