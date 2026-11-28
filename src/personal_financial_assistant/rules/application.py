"""Coherent per-occurrence decisions and review snapshots under caller-owned locks."""

import json
from dataclasses import asdict, dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from personal_financial_assistant.infrastructure.models import (
    ClassificationPreference,
    Merchant,
    MerchantDefault,
    MerchantMatch,
    OccurrenceEvidenceRevision,
    TransactionClassification,
    TransactionObservation,
    TransactionOverride,
    occurrence_observation,
)

from .categories import (
    CategoryCandidate,
    CategoryRule,
    applicable_categories,
    select_category,
)
from .conflicts import (
    ApprovalScope,
    ConflictCandidate,
    ConflictPair,
    ConflictResolution,
    detect_application_conflicts,
)
from .matching import (
    MerchantMatchCandidate,
    find_matching_entries,
    resolve_merchant_matches,
)
from .types import (
    BlockedAIConflict,
    EntryKind,
    EvaluationResult,
    MatchKind,
    MerchantDecision,
    MerchantResolved,
    PreferenceKind,
    ProposalOrigin,
    RuleReference,
)


@dataclass(frozen=True)
class PreparedApplication:
    result: EvaluationResult
    snapshot: dict[str, object] = field(repr=False)
    scopes: dict[int, ApprovalScope]
    matching_candidates: tuple[RuleReference, ...]


@dataclass(frozen=True)
class PreparedMerchant:
    evidence_revision: int
    fields: list[str | None] = field(repr=False)
    decision: MerchantDecision
    candidates: list[ConflictCandidate]
    resolution: ConflictResolution
    blocked: tuple[BlockedAIConflict, ...]


def _unblocked(
    resolution: ConflictResolution, hypothetical_approval: int | None
) -> tuple[set[RuleReference], tuple[BlockedAIConflict, ...]]:
    remaining = tuple(
        pair for pair in resolution.blocked if pair.conflict_id != hypothetical_approval
    )
    blocked = {pair.ai_entry for pair in remaining}
    references = {candidate.reference for candidate in resolution.eligible} | {
        pair.ai_entry for pair in resolution.blocked if pair.ai_entry not in blocked
    }
    return references, remaining


def _pair_state(pair: ConflictPair) -> dict[str, object]:
    return {
        "id": pair.conflict_id,
        "state": pair.state,
        "approved": pair.approved,
        "scope": asdict(pair.scope),
    }


def _merchant_ids(row: MerchantDefault | ClassificationPreference) -> tuple[int, ...]:
    merchant_id = row.merchant_id
    return (merchant_id,) if merchant_id is not None else ()


async def prepare_merchant(
    session: AsyncSession,
    occurrence_id: int,
    *,
    hypothetical_approval: int | None = None,
) -> PreparedMerchant:
    """Resolve merchant candidates while the caller owns both required locks."""
    evidence = await session.get(OccurrenceEvidenceRevision, occurrence_id)
    if evidence is None:
        evidence = OccurrenceEvidenceRevision(occurrence_id=occurrence_id, revision=1)
        session.add(evidence)
        await session.flush()
    observations = (
        await session.execute(
            select(TransactionObservation.operation, TransactionObservation.details)
            .join(
                occurrence_observation,
                occurrence_observation.c.observation_id == TransactionObservation.id,
            )
            .where(occurrence_observation.c.occurrence_id == occurrence_id)
            .order_by(TransactionObservation.id)
        )
    ).all()
    fields = [value for row in observations for value in row]
    matches = (
        await session.scalars(
            select(MerchantMatch)
            .join(Merchant, Merchant.id == MerchantMatch.merchant_id)
            .where(Merchant.enabled.is_(True), MerchantMatch.enabled.is_(True))
            .order_by(MerchantMatch.id)
        )
    ).all()
    matching = find_matching_entries(
        fields,
        [
            MerchantMatchCandidate(
                RuleReference(EntryKind.MATCHING_ENTRY, row.id),
                row.merchant_id,
                MatchKind(row.kind),
                row.normalized_text,
            )
            for row in matches
        ],
    )
    match_rows = {row.id: row for row in matches}
    match_conflicts = [
        ConflictCandidate(
            candidate.reference,
            match_rows[candidate.reference.id].revision,
            ProposalOrigin(match_rows[candidate.reference.id].origin),
            match_rows[candidate.reference.id].confirmed,
            candidate.merchant_id,
            (candidate.merchant_id,),
        )
        for candidate in matching
    ]
    match_resolution = await detect_application_conflicts(
        session, occurrence_id, evidence.revision, "merchant", match_conflicts
    )
    eligible_matches, blocked_matches = _unblocked(
        match_resolution, hypothetical_approval
    )
    merchant = resolve_merchant_matches(
        [candidate for candidate in matching if candidate.reference in eligible_matches]
    )
    return PreparedMerchant(
        evidence.revision,
        fields,
        merchant,
        match_conflicts,
        match_resolution,
        blocked_matches,
    )


async def prepare_application(
    session: AsyncSession,
    occurrence_id: int,
    *,
    hypothetical_approval: int | None = None,
) -> PreparedApplication:
    """Evaluate all candidates; caller must hold configuration and occurrence locks.

    The optional hypothetical approval removes only that pair's block from the
    displayed decision; it does not create an approval or write a classification.
    """
    current = (
        await prepare_application(session, occurrence_id)
        if hypothetical_approval is not None
        else None
    )
    prepared_merchant = await prepare_merchant(
        session, occurrence_id, hypothetical_approval=hypothetical_approval
    )
    merchant = prepared_merchant.decision
    fields = prepared_merchant.fields
    match_conflicts = prepared_merchant.candidates
    match_resolution = prepared_merchant.resolution
    blocked_matches = prepared_merchant.blocked
    merchant_id = (
        merchant.merchant_id if isinstance(merchant, MerchantResolved) else None
    )

    defaults = (
        await session.scalars(
            select(MerchantDefault)
            .join(Merchant, Merchant.id == MerchantDefault.merchant_id)
            .where(
                MerchantDefault.enabled.is_(True),
                Merchant.enabled.is_(True),
                MerchantDefault.merchant_id == merchant_id,
            )
            .order_by(MerchantDefault.id)
        )
    ).all()
    preferences = (
        await session.scalars(
            select(ClassificationPreference)
            .outerjoin(Merchant, Merchant.id == ClassificationPreference.merchant_id)
            .where(
                ClassificationPreference.enabled.is_(True),
                or_(
                    ClassificationPreference.merchant_id.is_(None),
                    Merchant.enabled.is_(True),
                ),
            )
            .order_by(ClassificationPreference.id)
        )
    ).all()
    rules: list[CategoryRule] = [
        CategoryRule(
            CategoryCandidate(
                RuleReference(EntryKind.MERCHANT_DEFAULT, row.id),
                row.category,
                None,
                row.confirmed,
            ),
            merchant_id=row.merchant_id,
        )
        for row in defaults
    ]
    rules.extend(
        CategoryRule(
            CategoryCandidate(
                RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, row.id),
                row.category,
                PreferenceKind(row.match_kind),
                row.confirmed,
            ),
            merchant_id=row.merchant_id,
            match_text=row.match_text,
        )
        for row in preferences
    )
    applicable = applicable_categories(fields, merchant_id, rules)
    category_rows = {
        **{RuleReference(EntryKind.MERCHANT_DEFAULT, row.id): row for row in defaults},
        **{
            RuleReference(EntryKind.CLASSIFICATION_PREFERENCE, row.id): row
            for row in preferences
        },
    }
    category_conflicts = [
        ConflictCandidate(
            candidate.reference,
            category_rows[candidate.reference].revision,
            ProposalOrigin(category_rows[candidate.reference].origin),
            candidate.confirmed,
            candidate.category,
            _merchant_ids(category_rows[candidate.reference]),
        )
        for candidate in applicable
    ]
    category_resolution = await detect_application_conflicts(
        session,
        occurrence_id,
        prepared_merchant.evidence_revision,
        "category",
        category_conflicts,
    )
    eligible_categories, blocked_categories = _unblocked(
        category_resolution, hypothetical_approval
    )
    override = await session.get(TransactionOverride, occurrence_id)
    selection = select_category(
        occurrence_id,
        override.category if override is not None else None,
        [
            candidate
            for candidate in applicable
            if candidate.reference in eligible_categories
        ],
    )
    classification = await session.get(
        TransactionClassification, (occurrence_id, "category")
    )
    pairs = (*match_resolution.pairs, *category_resolution.pairs)
    merchant_ids = {
        merchant_id
        for candidate in (*match_conflicts, *category_conflicts)
        for merchant_id in candidate.merchant_ids
    }
    merchant_revisions = (
        await session.execute(
            select(Merchant.id, Merchant.enabled_revision)
            .where(Merchant.id.in_(merchant_ids))
            .order_by(Merchant.id)
        )
    ).all()
    result = EvaluationResult(
        occurrence_id,
        prepared_merchant.evidence_revision,
        merchant,
        selection.decision,
        selection.conflict_candidates,
        (*blocked_matches, *blocked_categories),
    )
    snapshot: dict[str, object] = {
        "occurrence_id": occurrence_id,
        "evidence_revision": prepared_merchant.evidence_revision,
        "matching_candidates": [asdict(candidate) for candidate in match_conflicts],
        "category_candidates": [asdict(candidate) for candidate in category_conflicts],
        "merchant_revisions": [
            [row.id, row.enabled_revision] for row in merchant_revisions
        ],
        "override": (
            {"category": override.category, "revision": override.revision}
            if override is not None
            else None
        ),
        "category": (
            {
                "value": classification.value,
                "status": classification.status,
                "source": classification.source,
                "confidence": str(classification.confidence)
                if classification.confidence is not None
                else None,
            }
            if classification is not None
            else None
        ),
        "conflicts": [_pair_state(pair) for pair in pairs],
        "result": asdict(result),
        "current_evaluation": current.snapshot if current is not None else None,
    }
    serialized_snapshot: dict[str, object] = json.loads(json.dumps(snapshot))
    return PreparedApplication(
        result,
        serialized_snapshot,
        {pair.conflict_id: pair.scope for pair in pairs},
        tuple(candidate.reference for candidate in match_conflicts),
    )
