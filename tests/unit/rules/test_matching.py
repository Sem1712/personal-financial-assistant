import pytest

from personal_financial_assistant.rules.matching import (
    MerchantMatchCandidate,
    match_merchants,
)
from personal_financial_assistant.rules.types import (
    EntryKind,
    MatchKind,
    MerchantConflict,
    MerchantNoMatch,
    MerchantResolved,
    RuleReference,
)


def candidate(
    entry_id: int, merchant_id: int, kind: MatchKind, text: str
) -> MerchantMatchCandidate:
    return MerchantMatchCandidate(
        reference=RuleReference(EntryKind.MATCHING_ENTRY, entry_id),
        merchant_id=merchant_id,
        kind=kind,
        normalized_text=text,
    )


@pytest.mark.parametrize("number", range(100))
def test_synthetic_descriptions_normalize_without_losing_punctuation(
    number: int,
) -> None:
    fields = [f"  STRASSE\t SHOP-{number:03}\n", None]
    entry = candidate(1, 4, MatchKind.ALIAS, f"strasse shop-{number:03}")
    assert match_merchants(fields, [entry]) == MerchantResolved(
        merchant_id=4, winning_entries=(entry.reference,)
    )


def test_exact_alias_beats_more_specific_substring() -> None:
    alias = candidate(1, 4, MatchKind.ALIAS, "straße shop".casefold())
    substring = candidate(2, 5, MatchKind.SUBSTRING, "shop")
    assert match_merchants(["  STRASSE   SHOP ", None], [substring, alias]) == (
        MerchantResolved(merchant_id=4, winning_entries=(alias.reference,))
    )


@pytest.mark.parametrize("fields", [[], [None, " \t"], ["shop", "other"]])
def test_no_matching_fields_do_not_fabricate_concatenated_text(
    fields: list[str | None],
) -> None:
    assert (
        match_merchants(fields, [candidate(1, 1, MatchKind.ALIAS, "shop other")])
        == MerchantNoMatch()
    )


def test_exact_match_does_not_match_part_of_a_field() -> None:
    assert (
        match_merchants(["the shop"], [candidate(1, 1, MatchKind.ALIAS, "shop")])
        == MerchantNoMatch()
    )


def test_multiple_fields_can_match_one_merchant() -> None:
    first = candidate(5, 1, MatchKind.ALIAS, "shop a")
    second = candidate(2, 1, MatchKind.ALIAS, "shop b")
    result = match_merchants(["shop a", "shop b"], [first, second])
    assert result == MerchantResolved(
        merchant_id=1, winning_entries=(second.reference, first.reference)
    )


def test_same_priority_different_merchants_are_a_conflict() -> None:
    first = candidate(5, 1, MatchKind.SUBSTRING, "shop")
    second = candidate(2, 2, MatchKind.SUBSTRING, "shop")
    result = match_merchants(["shop card payment"], [first, second])
    assert result == MerchantConflict(candidates=(second.reference, first.reference))
