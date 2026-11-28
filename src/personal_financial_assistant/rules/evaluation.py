"""Occurrence-based merchant and category evaluation under rule and evidence locks."""

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.transactions import (
    ClassificationInput,
    EnrichmentUpdate,
    apply_enrichment_in_session,
)

from .application import prepare_application, prepare_merchant
from .storage import rules_transaction
from .types import (
    CategoryApplied,
    CategoryOverride,
    EvaluationResult,
    MerchantDecision,
)


async def identify_merchant(
    bind: AsyncEngine | AsyncConnection, occurrence_id: int
) -> MerchantDecision:
    """Identify a merchant without changing source evidence or classifications."""
    async with rules_transaction(bind, occurrence_id=occurrence_id) as session:
        return (await prepare_merchant(session, occurrence_id)).decision


async def evaluate_in_session(
    session: AsyncSession, occurrence_id: int
) -> EvaluationResult:
    """Evaluate under caller-owned configuration and occurrence locks."""
    result = (await prepare_application(session, occurrence_id)).result
    await apply_evaluation_in_session(session, result)
    return result


async def apply_evaluation_in_session(
    session: AsyncSession, result: EvaluationResult
) -> None:
    """Apply a prepared decision in its original locked transaction."""
    decision = result.category
    if isinstance(decision, CategoryOverride):
        classification = ClassificationInput(
            value=decision.value, source="user", status="confirmed", confidence=None
        )
    elif isinstance(decision, CategoryApplied):
        classification = ClassificationInput(
            value=decision.value, source="rule", status=decision.status, confidence=None
        )
    else:
        classification = None
    if classification is not None:
        await apply_enrichment_in_session(
            session, result.occurrence_id, EnrichmentUpdate(category=classification)
        )


async def evaluate_rules(
    bind: AsyncEngine | AsyncConnection, occurrence_id: int
) -> EvaluationResult:
    """Evaluate one occurrence atomically with per-occurrence AI safeguards."""
    async with rules_transaction(bind, occurrence_id=occurrence_id) as session:
        return await evaluate_in_session(session, occurrence_id)
