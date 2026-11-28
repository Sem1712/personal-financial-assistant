"""Trusted automated rule proposals; confirmed decisions require explicit review."""

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import (
    ChangeSuggestion,
    ClassificationPreference,
    Merchant,
    MerchantDefault,
    MerchantMatch,
)

from .categories import (
    create_merchant_default_in_session,
    create_preference_in_session,
)
from .merchants import MerchantRecord, create_matching_entry_in_session
from .storage import rules_transaction
from .types import (
    EntryKind,
    GeneratedProposal,
    MatchingEntryInput,
    MerchantDefaultInput,
    MerchantInput,
    PreferenceInput,
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
class ProposedRuleRecord:
    id: int
    reference: RuleReference
    origin: str
    confirmed: bool
    revision: int


@dataclass(frozen=True)
class ChangeSuggestionRecord:
    id: int
    target_kind: str
    target_id: int
    target_revision: int
    action: str
    origin: str
    state: str


def _automated_origin[T](proposal: GeneratedProposal[T]) -> ProposalOrigin:
    if (
        type(proposal) is not GeneratedProposal
        or type(proposal.origin) is not ProposalOrigin
    ):
        raise RuleValidationError("Unknown proposal provenance")
    if proposal.origin is ProposalOrigin.USER:
        raise RuleValidationError("Automated proposals cannot use user origin")
    return proposal.origin


async def propose_merchant(
    bind: Database, proposal: GeneratedProposal[MerchantInput]
) -> MerchantRecord:
    """Create a merchant without inferring any user confirmation."""
    _automated_origin(proposal)
    data = MerchantInput(proposal.value.canonical_name)
    async with rules_transaction(bind) as session:
        row = Merchant(canonical_name=data.canonical_name)
        session.add(row)
        await session.flush()
        return MerchantRecord(row.id, row.canonical_name, row.enabled, row.revision)


async def propose_matching_entry(
    bind: Database, proposal: GeneratedProposal[MatchingEntryInput]
) -> ProposedRuleRecord:
    """Create an unconfirmed matching entry with tracked origin."""
    origin = _automated_origin(proposal)
    async with rules_transaction(bind) as session:
        row = await create_matching_entry_in_session(session, proposal.value, origin)
        return ProposedRuleRecord(
            row.id,
            RuleReference(EntryKind.MATCHING_ENTRY, row.id),
            row.origin,
            row.confirmed,
            row.revision,
        )


async def propose_merchant_default(
    bind: Database, proposal: GeneratedProposal[MerchantDefaultInput]
) -> ProposedRuleRecord:
    """Create an unconfirmed merchant default with tracked origin."""
    origin = _automated_origin(proposal)
    async with rules_transaction(bind) as session:
        row = await create_merchant_default_in_session(session, proposal.value, origin)
        return ProposedRuleRecord(
            row.id,
            RuleReference(EntryKind.MERCHANT_DEFAULT, row.id),
            row.origin,
            row.confirmed,
            row.revision,
        )


async def propose_preference(
    bind: Database, proposal: GeneratedProposal[PreferenceInput]
) -> ProposedRuleRecord:
    """Create an unconfirmed preference from trusted generation provenance."""
    origin = _automated_origin(proposal)
    data = proposal.value
    data = PreferenceInput(data.kind, data.category, data.merchant_id, data.match_text)
    async with rules_transaction(bind) as session:
        row = await create_preference_in_session(session, data, origin)
        return ProposedRuleRecord(
            id=row.id,
            reference=RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, row.id),
            origin=row.origin,
            confirmed=row.confirmed,
            revision=row.revision,
        )


async def _has_confirmed_rules(session: AsyncSession, merchant_id: int) -> bool:
    for model in (MerchantMatch, MerchantDefault, ClassificationPreference):
        found = await session.scalar(
            select(
                exists().where(
                    model.merchant_id == merchant_id, model.confirmed.is_(True)
                )
            )
        )
        if found:
            return True
    return False


type RuleChangeInput = (
    MatchingEntryInput | MerchantDefaultInput | PreferenceInput | None
)
type RuleRow = MerchantMatch | MerchantDefault | ClassificationPreference


async def get_rule_in_session(
    session: AsyncSession, reference: RuleReference
) -> RuleRow:
    """Fetch a typed rule within the caller's locked transaction."""
    if reference.kind is EntryKind.MATCHING_ENTRY:
        row = await session.get(MerchantMatch, reference.id)
    elif reference.kind is EntryKind.MERCHANT_DEFAULT:
        row = await session.get(MerchantDefault, reference.id)
    else:
        row = await session.get(ClassificationPreference, reference.id)
    if row is None:
        raise RuleNotFound("Rule not found")
    return row


async def validate_change_in_session(
    session: AsyncSession, row: RuleRow, data: RuleChangeInput
) -> tuple[RuleChangeInput, dict[str, object]]:
    """Validate an edit and return its safe-to-persist payload."""
    if data is None:
        return None, {}
    if isinstance(row, MerchantMatch) and isinstance(data, MatchingEntryInput):
        data = MatchingEntryInput(data.merchant_id, data.kind, data.text)
        if await session.get(Merchant, data.merchant_id) is None:
            raise RuleNotFound("Merchant not found")
        normalized = normalize_description(data.text)
        duplicate = await session.scalar(
            select(MerchantMatch.id).where(
                MerchantMatch.merchant_id == data.merchant_id,
                MerchantMatch.kind == data.kind.value,
                MerchantMatch.normalized_text == normalized,
                MerchantMatch.id != row.id,
            )
        )
        if duplicate is not None:
            raise RuleValidationError("Duplicate merchant matching entry")
        return data, {
            "merchant_id": data.merchant_id,
            "kind": data.kind.value,
            "text": data.text,
        }
    if isinstance(row, MerchantDefault) and isinstance(data, MerchantDefaultInput):
        data = MerchantDefaultInput(data.merchant_id, data.category)
        if await session.get(Merchant, data.merchant_id) is None:
            raise RuleNotFound("Merchant not found")
        duplicate = await session.scalar(
            select(MerchantDefault.id).where(
                MerchantDefault.merchant_id == data.merchant_id,
                MerchantDefault.id != row.id,
            )
        )
        if duplicate is not None:
            raise RuleValidationError("Merchant already has a default")
        return data, {"merchant_id": data.merchant_id, "category": data.category}
    if isinstance(row, ClassificationPreference) and isinstance(data, PreferenceInput):
        data = PreferenceInput(
            data.kind, data.category, data.merchant_id, data.match_text
        )
        if (
            data.merchant_id is not None
            and await session.get(Merchant, data.merchant_id) is None
        ):
            raise RuleNotFound("Merchant not found")
        return data, {
            "kind": data.kind.value,
            "merchant_id": data.merchant_id,
            "match_text": data.match_text,
            "category": data.category,
        }
    raise RuleValidationError("Proposal does not match rule kind")


def apply_change_to_row(
    row: RuleRow, data: RuleChangeInput, origin: ProposalOrigin
) -> None:
    """Apply a validated change within a transaction owned by the caller."""
    if data is None:
        if row.enabled:
            row.enabled = False
            row.revision += 1
        return
    if isinstance(row, MerchantMatch) and isinstance(data, MatchingEntryInput):
        row.merchant_id = data.merchant_id
        row.kind = data.kind.value
        row.original_text = data.text
        row.normalized_text = normalize_description(data.text)
    elif isinstance(row, MerchantDefault) and isinstance(data, MerchantDefaultInput):
        row.merchant_id = data.merchant_id
        row.category = data.category
    elif isinstance(row, ClassificationPreference) and isinstance(
        data, PreferenceInput
    ):
        row.match_kind = data.kind.value
        row.merchant_id = data.merchant_id
        row.match_text = (
            normalize_description(data.match_text)
            if data.match_text is not None
            else None
        )
        row.category = data.category
    else:
        raise RuleValidationError("Proposal does not match rule kind")
    row.origin = origin.value
    row.revision += 1


async def propose_rule_change(
    bind: Database,
    reference: RuleReference,
    expected_revision: int,
    proposal: GeneratedProposal[RuleChangeInput],
) -> ChangeSuggestionRecord | ProposedRuleRecord:
    """Propose an edit, or a disable when its value is None."""
    origin = _automated_origin(proposal)
    async with rules_transaction(bind) as session:
        row = await get_rule_in_session(session, reference)
        check_revision(row.revision, expected_revision)
        data, payload = await validate_change_in_session(session, row, proposal.value)
        if row.confirmed:
            if origin is not ProposalOrigin.AI:
                raise RuleValidationError("Confirmed rule requires user action")
            suggestion = ChangeSuggestion(
                target_kind=reference.kind.value,
                target_match_id=reference.id
                if reference.kind is EntryKind.MATCHING_ENTRY
                else None,
                target_default_id=reference.id
                if reference.kind is EntryKind.MERCHANT_DEFAULT
                else None,
                target_preference_id=reference.id
                if reference.kind is EntryKind.CLASSIFICATION_PREFERENCE
                else None,
                target_revision=row.revision,
                action="disable" if data is None else "edit",
                payload=payload,
                origin="ai",
                state="pending",
            )
            session.add(suggestion)
            await session.flush()
            return ChangeSuggestionRecord(
                suggestion.id,
                suggestion.target_kind,
                reference.id,
                row.revision,
                suggestion.action,
                suggestion.origin,
                suggestion.state,
            )
        apply_change_to_row(row, data, origin)
        await session.flush()
        return ProposedRuleRecord(
            row.id, reference, row.origin, row.confirmed, row.revision
        )


async def propose_merchant_default_edit(
    bind: Database,
    entry_id: int,
    expected_revision: int,
    proposal: GeneratedProposal[MerchantDefaultInput],
) -> ChangeSuggestionRecord | ProposedRuleRecord:
    """Queue an AI edit of a confirmed default instead of changing it."""
    origin = _automated_origin(proposal)
    return await propose_rule_change(
        bind,
        RuleReference(EntryKind.MERCHANT_DEFAULT, entry_id),
        expected_revision,
        GeneratedProposal[RuleChangeInput](proposal.value, origin),
    )


async def propose_merchant_disable(
    bind: Database,
    merchant_id: int,
    expected_revision: int,
    proposal: GeneratedProposal[bool],
) -> ChangeSuggestionRecord | MerchantRecord:
    """Queue an AI disable when it would suppress any confirmed merchant rule."""
    origin = _automated_origin(proposal)
    if proposal.value is not False:
        raise RuleValidationError("Expected a disable proposal")
    return await _propose_merchant_change(
        bind, merchant_id, expected_revision, origin, None
    )


async def propose_merchant_edit(
    bind: Database,
    merchant_id: int,
    expected_revision: int,
    proposal: GeneratedProposal[MerchantInput],
) -> ChangeSuggestionRecord | MerchantRecord:
    """Queue an AI rename when the merchant has confirmed rules."""
    origin = _automated_origin(proposal)
    data = MerchantInput(proposal.value.canonical_name)
    return await _propose_merchant_change(
        bind, merchant_id, expected_revision, origin, data
    )


async def _propose_merchant_change(
    bind: Database,
    merchant_id: int,
    expected_revision: int,
    origin: ProposalOrigin,
    data: MerchantInput | None,
) -> ChangeSuggestionRecord | MerchantRecord:
    validate_id(merchant_id)
    async with rules_transaction(bind) as session:
        row = await session.get(Merchant, merchant_id)
        if row is None:
            raise RuleNotFound("Merchant not found")
        check_revision(row.revision, expected_revision)
        changes_target = (
            row.enabled if data is None else row.canonical_name != data.canonical_name
        )
        if changes_target and await _has_confirmed_rules(session, merchant_id):
            if origin is not ProposalOrigin.AI:
                raise RuleValidationError("Confirmed rules require user action")
            suggestion = ChangeSuggestion(
                target_kind="merchant",
                target_merchant_id=row.id,
                target_revision=row.revision,
                action="disable" if data is None else "edit",
                payload={} if data is None else {"canonical_name": data.canonical_name},
                origin="ai",
                state="pending",
            )
            session.add(suggestion)
            await session.flush()
            return ChangeSuggestionRecord(
                suggestion.id,
                suggestion.target_kind,
                row.id,
                row.revision,
                suggestion.action,
                suggestion.origin,
                suggestion.state,
            )
        if changes_target and data is None:
            row.enabled = False
            row.revision += 1
            row.enabled_revision += 1
        elif changes_target and data is not None:
            row.canonical_name = data.canonical_name
            row.revision += 1
        await session.flush()
        return MerchantRecord(row.id, row.canonical_name, row.enabled, row.revision)
