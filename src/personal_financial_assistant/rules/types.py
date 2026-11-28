"""Typed rule references, outcomes, validation and trusted generation provenance."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import ValidationError

from personal_financial_assistant.transactions import (
    ClassificationInput,
    EnrichmentUpdate,
)


class RuleValidationError(ValueError):
    """A rule request is invalid; its message never contains input values."""


class RuleNotFound(Exception):
    """The requested rule or merchant does not exist."""


class StaleRuleRevision(Exception):
    """A rule changed since the caller last inspected it."""


class EntryKind(StrEnum):
    MATCHING_ENTRY = "matching_entry"
    MERCHANT_DEFAULT = "merchant_default"
    CLASSIFICATION_PREFERENCE = "classification_preference"


class ProposalOrigin(StrEnum):
    USER = "user"
    AI = "ai"
    SERVICE = "service"


class MatchKind(StrEnum):
    ALIAS = "alias"
    SUBSTRING = "substring"


class PreferenceKind(StrEnum):
    MERCHANT = "merchant"
    EXACT_DESCRIPTION = "exact_description"
    SUBSTRING_DESCRIPTION = "substring_description"


def validate_id(value: int) -> None:
    if type(value) is not int or value <= 0:
        raise RuleValidationError("Invalid ID")


def validate_correlation_id(value: object) -> UUID:
    if not isinstance(value, UUID):
        raise RuleValidationError("Invalid import correlation ID")
    return value


def check_revision(actual: int, expected: int) -> None:
    validate_id(expected)
    if actual != expected:
        raise StaleRuleRevision("Rule revision changed")


@dataclass(frozen=True)
class RuleReference:
    """A rule identity includes its kind because table-local IDs can overlap."""

    kind: EntryKind
    id: int

    def __post_init__(self) -> None:
        if type(self.kind) is not EntryKind:
            raise RuleValidationError("Invalid rule kind")
        validate_id(self.id)


@dataclass(frozen=True)
class GeneratedProposal[T]:
    """Value with provenance set by the trusted host, not by model output."""

    value: T = field(repr=False)
    origin: ProposalOrigin

    def __post_init__(self) -> None:
        if type(self.origin) is not ProposalOrigin:
            raise RuleValidationError("Unknown proposal provenance")

    @staticmethod
    def from_trusted[V](value: V, origin: str) -> GeneratedProposal[V]:
        """Construct from host-tracked provenance; never pass model-supplied origin."""
        try:
            provenance = ProposalOrigin(origin)
        except ValueError:
            raise RuleValidationError("Unknown proposal provenance") from None
        return GeneratedProposal(value=value, origin=provenance)

    def transform[U](self, function: Callable[[T], U]) -> GeneratedProposal[U]:
        """Transform a proposal without relabeling its generation origin."""
        return GeneratedProposal(value=function(self.value), origin=self.origin)


def normalize_description(value: str) -> str:
    """Case-fold and collapse whitespace without combining observation fields."""
    return " ".join(value.casefold().split())


def validate_category(value: str) -> str:
    """Reuse transaction category validation without including payloads in errors."""
    try:
        classification = ClassificationInput(
            value=value, status="confirmed", source="user"
        )
        EnrichmentUpdate(category=classification)
    except ValidationError:
        raise RuleValidationError("Invalid rule text or category") from None
    return classification.value


def validate_rule_text(value: str) -> str:
    """Validate a nonempty matching text while preserving its original spelling."""
    return validate_category(value)


@dataclass(frozen=True)
class MerchantInput:
    canonical_name: str = field(repr=False)

    def __post_init__(self) -> None:
        validate_rule_text(self.canonical_name)


@dataclass(frozen=True)
class MatchingEntryInput:
    merchant_id: int
    kind: MatchKind
    text: str = field(repr=False)

    def __post_init__(self) -> None:
        validate_id(self.merchant_id)
        if type(self.kind) is not MatchKind:
            raise RuleValidationError("Invalid matching kind")
        validate_rule_text(self.text)


@dataclass(frozen=True)
class MerchantDefaultInput:
    merchant_id: int
    category: str = field(repr=False)

    def __post_init__(self) -> None:
        validate_id(self.merchant_id)
        validate_category(self.category)


@dataclass(frozen=True)
class PreferenceInput:
    kind: PreferenceKind
    category: str = field(repr=False)
    merchant_id: int | None = None
    match_text: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.kind) is not PreferenceKind:
            raise RuleValidationError("Invalid preference kind")
        validate_category(self.category)
        if self.kind is PreferenceKind.MERCHANT:
            if self.merchant_id is None or self.match_text is not None:
                raise RuleValidationError("Invalid preference operand")
            validate_id(self.merchant_id)
        else:
            if self.merchant_id is not None or self.match_text is None:
                raise RuleValidationError("Invalid preference operand")
            validate_rule_text(self.match_text)


@dataclass(frozen=True)
class MerchantResolved:
    merchant_id: int
    winning_entries: tuple[RuleReference, ...]
    status: Literal["resolved"] = field(default="resolved", init=False)


@dataclass(frozen=True)
class MerchantNoMatch:
    status: Literal["no_match"] = field(default="no_match", init=False)


@dataclass(frozen=True)
class MerchantConflict:
    candidates: tuple[RuleReference, ...]
    status: Literal["conflict"] = field(default="conflict", init=False)


type MerchantDecision = MerchantResolved | MerchantNoMatch | MerchantConflict


@dataclass(frozen=True)
class CategoryOverride:
    value: str = field(repr=False)
    occurrence_id: int
    kind: Literal["override"] = field(default="override", init=False)


@dataclass(frozen=True)
class CategoryApplied:
    value: str = field(repr=False)
    winning_rules: tuple[RuleReference, ...]
    status: Literal["confirmed", "provisional"]
    kind: Literal["applied"] = field(default="applied", init=False)


@dataclass(frozen=True)
class CategoryUnchanged:
    reason: Literal["no_rule", "conflict"]
    kind: Literal["unchanged"] = field(default="unchanged", init=False)


type CategoryDecision = CategoryOverride | CategoryApplied | CategoryUnchanged


@dataclass(frozen=True)
class BlockedAIConflict:
    conflict_id: int
    ai_entry: RuleReference
    confirmed_entry: RuleReference


@dataclass(frozen=True)
class EvaluationResult:
    occurrence_id: int
    evidence_revision: int
    merchant: MerchantDecision
    category: CategoryDecision
    category_conflict_candidates: tuple[RuleReference, ...]
    blocked_ai_conflicts: tuple[BlockedAIConflict, ...]
