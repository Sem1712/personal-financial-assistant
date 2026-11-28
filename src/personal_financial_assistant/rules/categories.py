"""User-directed category rules and deterministic category precedence."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import (
    ClassificationPreference,
    Merchant,
    MerchantDefault,
)

from .storage import rules_transaction
from .types import (
    CategoryApplied,
    CategoryDecision,
    CategoryOverride,
    CategoryUnchanged,
    EntryKind,
    MerchantDefaultInput,
    PreferenceInput,
    PreferenceKind,
    ProposalOrigin,
    RuleNotFound,
    RuleReference,
    RuleValidationError,
    check_revision,
    normalize_description,
    validate_category,
    validate_id,
    validate_rule_text,
)

type Database = AsyncEngine | AsyncConnection


@dataclass(frozen=True)
class CategoryCandidate:
    reference: RuleReference
    category: str = field(repr=False)
    preference_kind: PreferenceKind | None
    confirmed: bool

    def __post_init__(self) -> None:
        expected = (
            EntryKind.MERCHANT_DEFAULT
            if self.preference_kind is None
            else EntryKind.CLASSIFICATION_PREFERENCE
        )
        if self.reference.kind is not expected:
            raise RuleValidationError("Invalid category rule reference")
        if (
            self.preference_kind is not None
            and type(self.preference_kind) is not PreferenceKind
        ):
            raise RuleValidationError("Invalid preference kind")
        if type(self.confirmed) is not bool:
            raise RuleValidationError("Invalid confirmation state")
        validate_category(self.category)


@dataclass(frozen=True)
class CategoryRule:
    candidate: CategoryCandidate
    merchant_id: int | None = None
    match_text: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.candidate.preference_kind in (None, PreferenceKind.MERCHANT):
            if self.merchant_id is None or self.match_text is not None:
                raise RuleValidationError("Invalid category rule operand")
            validate_id(self.merchant_id)
        else:
            if self.merchant_id is not None or self.match_text is None:
                raise RuleValidationError("Invalid category rule operand")
            validate_rule_text(self.match_text)
            if self.match_text != normalize_description(self.match_text):
                raise RuleValidationError("Category matching text is not normalized")


@dataclass(frozen=True)
class CategorySelection:
    decision: CategoryDecision
    conflict_candidates: tuple[RuleReference, ...] = ()


def applicable_categories(
    fields: Sequence[str | None], merchant_id: int | None, rules: Sequence[CategoryRule]
) -> tuple[CategoryCandidate, ...]:
    """Collect category rules applicable to separate observation fields."""
    descriptions = tuple(
        normalized
        for value in fields
        if value is not None and (normalized := normalize_description(value))
    )
    applicable: list[CategoryCandidate] = []
    for rule in rules:
        kind = rule.candidate.preference_kind
        if kind in (None, PreferenceKind.MERCHANT):
            matched = merchant_id is not None and rule.merchant_id == merchant_id
        elif kind is PreferenceKind.EXACT_DESCRIPTION:
            matched = rule.match_text in descriptions
        else:
            assert rule.match_text is not None
            matched = any(
                rule.match_text in description for description in descriptions
            )
        if matched:
            applicable.append(rule.candidate)
    return tuple(applicable)


def select_category(
    occurrence_id: int, override: str | None, candidates: Sequence[CategoryCandidate]
) -> CategorySelection:
    """Apply override, preference specificity and confirmation precedence."""
    validate_id(occurrence_id)
    if override is not None:
        return CategorySelection(
            CategoryOverride(validate_category(override), occurrence_id)
        )
    if not candidates:
        return CategorySelection(CategoryUnchanged("no_rule"))

    def rank(candidate: CategoryCandidate) -> tuple[int, bool]:
        if candidate.preference_kind is None:
            return (0, candidate.confirmed)
        if candidate.preference_kind is PreferenceKind.SUBSTRING_DESCRIPTION:
            return (1, candidate.confirmed)
        return (2, candidate.confirmed)

    top_rank = max(rank(candidate) for candidate in candidates)
    winners = sorted(
        (candidate for candidate in candidates if rank(candidate) == top_rank),
        key=lambda candidate: (candidate.reference.kind.value, candidate.reference.id),
    )
    references = tuple(candidate.reference for candidate in winners)
    categories = {candidate.category for candidate in winners}
    if len(categories) != 1:
        return CategorySelection(CategoryUnchanged("conflict"), references)
    return CategorySelection(
        CategoryApplied(
            value=winners[0].category,
            winning_rules=references,
            status="confirmed"
            if all(item.confirmed for item in winners)
            else "provisional",
        )
    )


@dataclass(frozen=True)
class MerchantDefaultRecord:
    id: int
    merchant_id: int
    category: str = field(repr=False)
    origin: str
    confirmed: bool
    enabled: bool
    revision: int

    @property
    def reference(self) -> RuleReference:
        return RuleReference(EntryKind.MERCHANT_DEFAULT, self.id)


@dataclass(frozen=True)
class PreferenceRecord:
    id: int
    kind: PreferenceKind
    merchant_id: int | None
    match_text: str | None = field(repr=False)
    category: str = field(repr=False)
    origin: str
    confirmed: bool
    enabled: bool
    revision: int

    @property
    def reference(self) -> RuleReference:
        return RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, self.id)


def _default_record(row: MerchantDefault) -> MerchantDefaultRecord:
    return MerchantDefaultRecord(
        row.id,
        row.merchant_id,
        row.category,
        row.origin,
        row.confirmed,
        row.enabled,
        row.revision,
    )


def _preference_record(row: ClassificationPreference) -> PreferenceRecord:
    return PreferenceRecord(
        row.id,
        PreferenceKind(row.match_kind),
        row.merchant_id,
        row.match_text,
        row.category,
        row.origin,
        row.confirmed,
        row.enabled,
        row.revision,
    )


async def _merchant_exists(session: AsyncSession, merchant_id: int) -> None:
    validate_id(merchant_id)
    if await session.get(Merchant, merchant_id) is None:
        raise RuleNotFound("Merchant not found")


async def _default(session: AsyncSession, entry_id: int) -> MerchantDefault:
    validate_id(entry_id)
    row = await session.get(MerchantDefault, entry_id)
    if row is None:
        raise RuleNotFound("Merchant default not found")
    return row


async def _preference(session: AsyncSession, entry_id: int) -> ClassificationPreference:
    validate_id(entry_id)
    row = await session.get(ClassificationPreference, entry_id)
    if row is None:
        raise RuleNotFound("Classification preference not found")
    return row


async def _check_default_unique(
    session: AsyncSession, merchant_id: int, exclude_id: int | None = None
) -> None:
    query = select(MerchantDefault.id).where(MerchantDefault.merchant_id == merchant_id)
    if exclude_id is not None:
        query = query.where(MerchantDefault.id != exclude_id)
    if await session.scalar(query) is not None:
        raise RuleValidationError("Merchant already has a default")


async def create_merchant_default(
    bind: Database, data: MerchantDefaultInput
) -> MerchantDefaultRecord:
    data = MerchantDefaultInput(data.merchant_id, data.category)
    async with rules_transaction(bind) as session:
        row = await create_merchant_default_in_session(
            session, data, ProposalOrigin.USER
        )
        return _default_record(row)


async def create_merchant_default_in_session(
    session: AsyncSession, data: MerchantDefaultInput, origin: ProposalOrigin
) -> MerchantDefault:
    """Insert an unconfirmed default using trusted, host-tracked provenance."""
    data = MerchantDefaultInput(data.merchant_id, data.category)
    if type(origin) is not ProposalOrigin:
        raise RuleValidationError("Unknown proposal provenance")
    await _merchant_exists(session, data.merchant_id)
    await _check_default_unique(session, data.merchant_id)
    row = MerchantDefault(
        merchant_id=data.merchant_id,
        category=data.category,
        origin=origin.value,
        confirmed=False,
    )
    session.add(row)
    await session.flush()
    return row


async def inspect_merchant_default(
    bind: Database, entry_id: int
) -> MerchantDefaultRecord:
    async with rules_transaction(bind) as session:
        return _default_record(await _default(session, entry_id))


async def edit_merchant_default(
    bind: Database, entry_id: int, expected_revision: int, data: MerchantDefaultInput
) -> MerchantDefaultRecord:
    data = MerchantDefaultInput(data.merchant_id, data.category)
    async with rules_transaction(bind) as session:
        row = await _default(session, entry_id)
        check_revision(row.revision, expected_revision)
        await _merchant_exists(session, data.merchant_id)
        await _check_default_unique(session, data.merchant_id, entry_id)
        row.merchant_id, row.category = data.merchant_id, data.category
        row.revision += 1
        await session.flush()
        return _default_record(row)


async def set_merchant_default_enabled(
    bind: Database, entry_id: int, expected_revision: int, enabled: bool
) -> MerchantDefaultRecord:
    if type(enabled) is not bool:
        raise RuleValidationError("Invalid enabled state")
    async with rules_transaction(bind) as session:
        row = await _default(session, entry_id)
        check_revision(row.revision, expected_revision)
        if row.enabled != enabled:
            row.enabled = enabled
            row.revision += 1
        await session.flush()
        return _default_record(row)


async def confirm_merchant_default(
    bind: Database, entry_id: int, expected_revision: int
) -> MerchantDefaultRecord:
    async with rules_transaction(bind) as session:
        row = await _default(session, entry_id)
        check_revision(row.revision, expected_revision)
        if not row.confirmed:
            row.confirmed = True
            row.revision += 1
        await session.flush()
        return _default_record(row)


async def create_preference(bind: Database, data: PreferenceInput) -> PreferenceRecord:
    data = PreferenceInput(data.kind, data.category, data.merchant_id, data.match_text)
    async with rules_transaction(bind) as session:
        row = await create_preference_in_session(session, data, ProposalOrigin.USER)
        return _preference_record(row)


async def create_preference_in_session(
    session: AsyncSession, data: PreferenceInput, origin: ProposalOrigin
) -> ClassificationPreference:
    """Insert an unconfirmed preference using provenance supplied by the trusted host."""
    data = PreferenceInput(data.kind, data.category, data.merchant_id, data.match_text)
    if type(origin) is not ProposalOrigin:
        raise RuleValidationError("Unknown proposal provenance")
    if data.merchant_id is not None:
        await _merchant_exists(session, data.merchant_id)
    row = ClassificationPreference(
        match_kind=data.kind.value,
        merchant_id=data.merchant_id,
        match_text=normalize_description(data.match_text)
        if data.match_text is not None
        else None,
        category=data.category,
        origin=origin.value,
        confirmed=False,
    )
    session.add(row)
    await session.flush()
    return row


async def inspect_preference(bind: Database, entry_id: int) -> PreferenceRecord:
    async with rules_transaction(bind) as session:
        return _preference_record(await _preference(session, entry_id))


async def edit_preference(
    bind: Database, entry_id: int, expected_revision: int, data: PreferenceInput
) -> PreferenceRecord:
    data = PreferenceInput(data.kind, data.category, data.merchant_id, data.match_text)
    async with rules_transaction(bind) as session:
        row = await _preference(session, entry_id)
        check_revision(row.revision, expected_revision)
        if data.merchant_id is not None:
            await _merchant_exists(session, data.merchant_id)
        row.match_kind = data.kind.value
        row.merchant_id = data.merchant_id
        row.match_text = (
            normalize_description(data.match_text)
            if data.match_text is not None
            else None
        )
        row.category = data.category
        row.revision += 1
        await session.flush()
        return _preference_record(row)


async def set_preference_enabled(
    bind: Database, entry_id: int, expected_revision: int, enabled: bool
) -> PreferenceRecord:
    if type(enabled) is not bool:
        raise RuleValidationError("Invalid enabled state")
    async with rules_transaction(bind) as session:
        row = await _preference(session, entry_id)
        check_revision(row.revision, expected_revision)
        if row.enabled != enabled:
            row.enabled = enabled
            row.revision += 1
        await session.flush()
        return _preference_record(row)


async def confirm_preference(
    bind: Database, entry_id: int, expected_revision: int
) -> PreferenceRecord:
    async with rules_transaction(bind) as session:
        row = await _preference(session, entry_id)
        check_revision(row.revision, expected_revision)
        if not row.confirmed:
            row.confirmed = True
            row.revision += 1
        await session.flush()
        return _preference_record(row)
