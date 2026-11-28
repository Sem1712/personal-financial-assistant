"""User-directed, occurrence-specific category overrides."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from personal_financial_assistant.infrastructure.models import TransactionOverride
from personal_financial_assistant.transactions import (
    ClassificationInput,
    EnrichmentUpdate,
    apply_enrichment_in_session,
)

from .storage import occurrence_transaction
from .types import validate_category

type Database = AsyncEngine | AsyncConnection


@dataclass(frozen=True)
class OverrideRecord:
    occurrence_id: int
    category: str = field(repr=False)
    revision: int


def _record(row: TransactionOverride) -> OverrideRecord:
    return OverrideRecord(row.occurrence_id, row.category, row.revision)


async def set_override(
    bind: Database, occurrence_id: int, category: str
) -> OverrideRecord:
    """Set an override and user-confirmed category in the same transaction."""
    category = validate_category(category)
    async with occurrence_transaction(bind, occurrence_id) as session:
        row = await session.get(TransactionOverride, occurrence_id)
        if row is None:
            row = TransactionOverride(occurrence_id=occurrence_id, category=category)
            session.add(row)
        elif row.category != category:
            row.category = category
            row.revision += 1
        await apply_enrichment_in_session(
            session,
            occurrence_id,
            EnrichmentUpdate(
                category=ClassificationInput(
                    value=category, source="user", status="confirmed", confidence=None
                )
            ),
        )
        await session.flush()
        return _record(row)


async def inspect_override(bind: Database, occurrence_id: int) -> OverrideRecord | None:
    async with occurrence_transaction(bind, occurrence_id) as session:
        row = await session.get(TransactionOverride, occurrence_id)
        return _record(row) if row is not None else None


async def clear_override(bind: Database, occurrence_id: int) -> bool:
    """Remove only the override; leave the current category unchanged."""
    async with occurrence_transaction(bind, occurrence_id) as session:
        row = await session.get(TransactionOverride, occurrence_id)
        if row is None:
            return False
        await session.delete(row)
        return True
