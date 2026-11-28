"""Pure matching of individual observation fields against literal merchant rules."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from .types import (
    EntryKind,
    MatchKind,
    MerchantConflict,
    MerchantDecision,
    MerchantNoMatch,
    MerchantResolved,
    RuleReference,
    RuleValidationError,
    normalize_description,
    validate_rule_text,
)


@dataclass(frozen=True)
class MerchantMatchCandidate:
    reference: RuleReference
    merchant_id: int
    kind: MatchKind
    normalized_text: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.reference.kind is not EntryKind.MATCHING_ENTRY:
            raise RuleValidationError("Invalid merchant matching reference")
        if type(self.merchant_id) is not int or self.merchant_id <= 0:
            raise RuleValidationError("Invalid merchant ID")
        if type(self.kind) is not MatchKind:
            raise RuleValidationError("Invalid matching kind")
        validate_rule_text(self.normalized_text)
        if self.normalized_text != normalize_description(self.normalized_text):
            raise RuleValidationError("Merchant matching text is not normalized")


def find_matching_entries(
    fields: Sequence[str | None], entries: Sequence[MerchantMatchCandidate]
) -> tuple[MerchantMatchCandidate, ...]:
    """Return all matching entries, considering each observation field separately."""
    descriptions = tuple(
        normalized
        for value in fields
        if value is not None and (normalized := normalize_description(value))
    )
    return tuple(
        entry
        for entry in entries
        if any(
            description == entry.normalized_text
            if entry.kind is MatchKind.ALIAS
            else entry.normalized_text in description
            for description in descriptions
        )
    )


def resolve_merchant_matches(
    matches: Sequence[MerchantMatchCandidate],
) -> MerchantDecision:
    """Resolve eligible matches by specificity, reporting same-rank ambiguity."""
    if not matches:
        return MerchantNoMatch()
    kind = (
        MatchKind.ALIAS
        if any(match.kind is MatchKind.ALIAS for match in matches)
        else MatchKind.SUBSTRING
    )
    winners = sorted(
        (match for match in matches if match.kind is kind),
        key=lambda item: item.reference.id,
    )
    references = tuple(match.reference for match in winners)
    merchant_ids = {match.merchant_id for match in winners}
    if len(merchant_ids) != 1:
        return MerchantConflict(candidates=references)
    return MerchantResolved(
        merchant_id=winners[0].merchant_id, winning_entries=references
    )


def match_merchants(
    fields: Sequence[str | None], entries: Sequence[MerchantMatchCandidate]
) -> MerchantDecision:
    """Match literal aliases and substrings and resolve their merchant decision."""
    return resolve_merchant_matches(find_matching_entries(fields, entries))
