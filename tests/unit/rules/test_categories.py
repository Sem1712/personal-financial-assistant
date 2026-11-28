import pytest

from personal_financial_assistant.rules.categories import (
    CategoryCandidate,
    CategoryRule,
    applicable_categories,
    select_category,
)
from personal_financial_assistant.rules.types import (
    CategoryApplied,
    CategoryOverride,
    CategoryUnchanged,
    EntryKind,
    PreferenceKind,
    RuleReference,
)


def candidate(
    entry_id: int,
    category: str,
    preference_kind: PreferenceKind | None,
    confirmed: bool,
) -> CategoryCandidate:
    kind = (
        EntryKind.MERCHANT_DEFAULT
        if preference_kind is None
        else EntryKind.CLASSIFICATION_PREFERENCE
    )
    return CategoryCandidate(
        reference=RuleReference(kind, entry_id),
        category=category,
        preference_kind=preference_kind,
        confirmed=confirmed,
    )


def test_override_wins_even_with_conflicting_rules() -> None:
    first = candidate(1, "food", PreferenceKind.EXACT_DESCRIPTION, True)
    second = candidate(2, "travel", PreferenceKind.EXACT_DESCRIPTION, True)
    result = select_category(1, "personal", [first, second])
    assert result.decision == CategoryOverride(value="personal", occurrence_id=1)


@pytest.mark.parametrize(
    ("winning_kind", "losing_kind"),
    [
        (PreferenceKind.MERCHANT, None),
        (PreferenceKind.EXACT_DESCRIPTION, None),
        (PreferenceKind.SUBSTRING_DESCRIPTION, None),
        (PreferenceKind.MERCHANT, PreferenceKind.SUBSTRING_DESCRIPTION),
        (PreferenceKind.EXACT_DESCRIPTION, PreferenceKind.SUBSTRING_DESCRIPTION),
    ],
)
def test_preference_specificity_precedes_confirmation(
    winning_kind: PreferenceKind, losing_kind: PreferenceKind | None
) -> None:
    winner = candidate(1, "winner", winning_kind, False)
    loser = candidate(2, "loser", losing_kind, True)
    selection = select_category(1, None, [loser, winner])
    assert selection.decision == CategoryApplied(
        value="winner", winning_rules=(winner.reference,), status="provisional"
    )
    assert not selection.conflict_candidates


def test_confirmed_wins_within_equal_preference_priority() -> None:
    winner = candidate(1, "food", PreferenceKind.MERCHANT, True)
    loser = candidate(2, "other", PreferenceKind.EXACT_DESCRIPTION, False)
    assert select_category(1, None, [loser, winner]).decision == CategoryApplied(
        value="food", winning_rules=(winner.reference,), status="confirmed"
    )


def test_equal_rank_same_category_keeps_all_winners() -> None:
    first = candidate(2, "food", PreferenceKind.MERCHANT, True)
    second = candidate(1, "food", PreferenceKind.EXACT_DESCRIPTION, True)
    assert select_category(1, None, [first, second]).decision == CategoryApplied(
        value="food",
        winning_rules=(second.reference, first.reference),
        status="confirmed",
    )


def test_equal_rank_different_categories_report_all_conflicts() -> None:
    first = candidate(2, "food", PreferenceKind.MERCHANT, True)
    second = candidate(1, "travel", PreferenceKind.EXACT_DESCRIPTION, True)
    selection = select_category(1, None, [first, second])
    assert selection.decision == CategoryUnchanged(reason="conflict")
    assert selection.conflict_candidates == (second.reference, first.reference)


def test_no_rule_preserves_current_category() -> None:
    assert select_category(1, None, []).decision == CategoryUnchanged(reason="no_rule")


def test_ambiguous_merchant_excludes_merchant_rules_not_description_rules() -> None:
    merchant_rule = CategoryRule(
        candidate=candidate(1, "merchant", PreferenceKind.MERCHANT, True),
        merchant_id=1,
    )
    description_rule = CategoryRule(
        candidate=candidate(2, "description", PreferenceKind.EXACT_DESCRIPTION, False),
        match_text="shop",
    )
    assert applicable_categories(["SHOP"], None, [merchant_rule, description_rule]) == (
        description_rule.candidate,
    )
