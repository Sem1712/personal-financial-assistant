"""User-directed lifecycle of merchants and literal matching entries."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import Merchant, MerchantMatch

from .storage import rules_transaction
from .types import (
    EntryKind,
    MatchingEntryInput,
    MatchKind,
    MerchantInput,
    ProposalOrigin,
    RuleNotFound,
    RuleReference,
    RuleValidationError,
    check_revision,
    normalize_description,
    validate_id,
)

type Database = AsyncEngine | AsyncConnection


@dataclass(frozen=True)
class MerchantRecord:
    id: int
    canonical_name: str = field(repr=False)
    enabled: bool
    revision: int


@dataclass(frozen=True)
class MatchingEntryRecord:
    id: int
    merchant_id: int
    kind: MatchKind
    original_text: str = field(repr=False)
    normalized_text: str = field(repr=False)
    origin: str
    confirmed: bool
    enabled: bool
    revision: int

    @property
    def reference(self) -> RuleReference:
        return RuleReference(EntryKind.MATCHING_ENTRY, self.id)


def _merchant_record(row: Merchant) -> MerchantRecord:
    return MerchantRecord(row.id, row.canonical_name, row.enabled, row.revision)


def _matching_record(row: MerchantMatch) -> MatchingEntryRecord:
    return MatchingEntryRecord(
        row.id,
        row.merchant_id,
        MatchKind(row.kind),
        row.original_text,
        row.normalized_text,
        row.origin,
        row.confirmed,
        row.enabled,
        row.revision,
    )


async def _merchant(session: AsyncSession, merchant_id: int) -> Merchant:
    validate_id(merchant_id)
    row = await session.get(Merchant, merchant_id)
    if row is None:
        raise RuleNotFound("Merchant not found")
    return row


async def _matching_entry(session: AsyncSession, entry_id: int) -> MerchantMatch:
    validate_id(entry_id)
    row = await session.get(MerchantMatch, entry_id)
    if row is None:
        raise RuleNotFound("Matching entry not found")
    return row


async def _check_duplicate(
    session: AsyncSession, data: MatchingEntryInput, *, exclude_id: int | None = None
) -> str:
    normalized = normalize_description(data.text)
    query = select(MerchantMatch.id).where(
        MerchantMatch.merchant_id == data.merchant_id,
        MerchantMatch.kind == data.kind.value,
        MerchantMatch.normalized_text == normalized,
    )
    if exclude_id is not None:
        query = query.where(MerchantMatch.id != exclude_id)
    if await session.scalar(query) is not None:
        raise RuleValidationError("Duplicate merchant matching entry")
    return normalized


async def create_merchant(bind: Database, data: MerchantInput) -> MerchantRecord:
    """Create a merchant on an explicit trusted user instruction."""
    data = MerchantInput(data.canonical_name)
    async with rules_transaction(bind) as session:
        row = Merchant(canonical_name=data.canonical_name)
        session.add(row)
        await session.flush()
        return _merchant_record(row)


async def inspect_merchant(bind: Database, merchant_id: int) -> MerchantRecord:
    async with rules_transaction(bind) as session:
        return _merchant_record(await _merchant(session, merchant_id))


async def edit_merchant(
    bind: Database, merchant_id: int, expected_revision: int, data: MerchantInput
) -> MerchantRecord:
    """Replace the name while checking the caller's last inspected revision."""
    data = MerchantInput(data.canonical_name)
    async with rules_transaction(bind) as session:
        row = await _merchant(session, merchant_id)
        check_revision(row.revision, expected_revision)
        row.canonical_name = data.canonical_name
        row.revision += 1
        await session.flush()
        return _merchant_record(row)


async def set_merchant_enabled(
    bind: Database, merchant_id: int, expected_revision: int, enabled: bool
) -> MerchantRecord:
    if type(enabled) is not bool:
        raise RuleValidationError("Invalid enabled state")
    async with rules_transaction(bind) as session:
        row = await _merchant(session, merchant_id)
        check_revision(row.revision, expected_revision)
        if row.enabled != enabled:
            row.enabled = enabled
            row.revision += 1
            row.enabled_revision += 1
        await session.flush()
        return _merchant_record(row)


async def create_matching_entry(
    bind: Database, data: MatchingEntryInput
) -> MatchingEntryRecord:
    """Create an unconfirmed user-origin entry; confirmation is separate."""
    data = MatchingEntryInput(data.merchant_id, data.kind, data.text)
    async with rules_transaction(bind) as session:
        row = await create_matching_entry_in_session(session, data, ProposalOrigin.USER)
        return _matching_record(row)


async def create_matching_entry_in_session(
    session: AsyncSession, data: MatchingEntryInput, origin: ProposalOrigin
) -> MerchantMatch:
    """Insert an unconfirmed match using trusted, host-tracked provenance."""
    data = MatchingEntryInput(data.merchant_id, data.kind, data.text)
    if type(origin) is not ProposalOrigin:
        raise RuleValidationError("Unknown proposal provenance")
    await _merchant(session, data.merchant_id)
    normalized = await _check_duplicate(session, data)
    row = MerchantMatch(
        merchant_id=data.merchant_id,
        kind=data.kind.value,
        original_text=data.text,
        normalized_text=normalized,
        origin=origin.value,
        confirmed=False,
    )
    session.add(row)
    await session.flush()
    return row


async def inspect_matching_entry(bind: Database, entry_id: int) -> MatchingEntryRecord:
    async with rules_transaction(bind) as session:
        return _matching_record(await _matching_entry(session, entry_id))


async def edit_matching_entry(
    bind: Database, entry_id: int, expected_revision: int, data: MatchingEntryInput
) -> MatchingEntryRecord:
    data = MatchingEntryInput(data.merchant_id, data.kind, data.text)
    async with rules_transaction(bind) as session:
        row = await _matching_entry(session, entry_id)
        check_revision(row.revision, expected_revision)
        await _merchant(session, data.merchant_id)
        normalized = await _check_duplicate(session, data, exclude_id=entry_id)
        row.merchant_id = data.merchant_id
        row.kind = data.kind.value
        row.original_text = data.text
        row.normalized_text = normalized
        row.revision += 1
        await session.flush()
        return _matching_record(row)


async def set_matching_entry_enabled(
    bind: Database, entry_id: int, expected_revision: int, enabled: bool
) -> MatchingEntryRecord:
    if type(enabled) is not bool:
        raise RuleValidationError("Invalid enabled state")
    async with rules_transaction(bind) as session:
        row = await _matching_entry(session, entry_id)
        check_revision(row.revision, expected_revision)
        if row.enabled != enabled:
            row.enabled = enabled
            row.revision += 1
        await session.flush()
        return _matching_record(row)


async def confirm_matching_entry(
    bind: Database, entry_id: int, expected_revision: int
) -> MatchingEntryRecord:
    """Explicitly confirm an entry without changing its generation origin."""
    async with rules_transaction(bind) as session:
        row = await _matching_entry(session, entry_id)
        check_revision(row.revision, expected_revision)
        if not row.confirmed:
            row.confirmed = True
            row.revision += 1
        await session.flush()
        return _matching_record(row)
