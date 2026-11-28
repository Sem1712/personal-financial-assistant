"""Read occurrence-based transaction history and its recorded source evidence."""

from datetime import date
from typing import cast

from pydantic import BaseModel
from sqlalchemy import Numeric, and_, func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import (
    TransactionClassification,
    TransactionContext,
    TransactionObservation,
    TransactionOccurrence,
    occurrence_observation,
)
from personal_financial_assistant.transactions.enrichment import (
    EnrichmentResult,
    build_result,
)
from personal_financial_assistant.transactions.filters import (
    CategoryValue,
    NoRecordedCategory,
    TransactionFilters,
)


class TransactionItem(BaseModel):
    id: str
    date: date
    amount_minor: str
    currency: str
    booking_status: str
    reconciliation_state: str
    ongoing_expense: bool
    operations: list[str]
    details: list[str]


class Observation(BaseModel):
    operation: str | None
    details: str | None
    category: str | None
    booking_status: str


class TransactionDetail(TransactionItem):
    observations: list[Observation]
    enrichment: EnrichmentResult


class TransactionPage(BaseModel):
    items: list[TransactionItem]
    next_cursor: str | None
    history_exists: bool


def _item(
    occurrence: TransactionOccurrence, operations: list[str], details: list[str]
) -> TransactionItem:
    return TransactionItem(
        id=str(occurrence.id),
        date=occurrence.transaction_date,
        amount_minor=str(occurrence.amount_minor),
        currency=occurrence.currency,
        booking_status=occurrence.booking_status or "unknown",
        reconciliation_state=occurrence.reconciliation_state,
        ongoing_expense=occurrence.is_ongoing_expense,
        operations=operations,
        details=details,
    )


async def search(engine: AsyncEngine, filters: TransactionFilters) -> TransactionPage:
    """Return a stable page with distinct recorded source text and history availability."""
    occurrence = TransactionOccurrence
    observation = TransactionObservation
    linked = occurrence_observation.join(
        observation, occurrence_observation.c.observation_id == observation.id
    )
    query = select(occurrence.id, occurrence.transaction_date)
    if filters.date_from is not None:
        query = query.where(occurrence.transaction_date >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(occurrence.transaction_date <= filters.date_to)
    if filters.booking_status == "unknown":
        query = query.where(occurrence.booking_status.is_(None))
    elif filters.booking_status is not None:
        query = query.where(occurrence.booking_status == filters.booking_status)
    # Neither bigint abs nor bigint bindings can represent the magnitude of -2^63.
    numeric_cents = Numeric(20, 0)
    magnitude = func.abs(occurrence.amount_minor.cast(numeric_cents))
    if filters.amount_min is not None:
        query = query.where(
            magnitude >= literal(filters.amount_min, type_=numeric_cents)
        )
    if filters.amount_max is not None:
        query = query.where(
            magnitude <= literal(filters.amount_max, type_=numeric_cents)
        )
    if filters.direction == "withdrawals":
        query = query.where(occurrence.amount_minor < 0)
    elif filters.direction == "deposits":
        query = query.where(occurrence.amount_minor > 0)
    if filters.text:
        text = (
            filters.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        text_match = (
            select(literal(1))
            .select_from(linked)
            .where(
                occurrence_observation.c.occurrence_id == occurrence.id,
                or_(
                    observation.operation.ilike(f"%{text}%", escape="\\"),
                    observation.details.ilike(f"%{text}%", escape="\\"),
                ),
            )
            .exists()
        )
        query = query.where(text_match)
    if filters.category is not None:
        category_match = (
            select(literal(1))
            .select_from(linked)
            .where(
                occurrence_observation.c.occurrence_id == occurrence.id,
                observation.category.is_not(None),
            )
        )
        if isinstance(filters.category, CategoryValue):
            category_match = category_match.where(
                observation.category == filters.category.value
            )
        if isinstance(filters.category, NoRecordedCategory):
            query = query.where(~category_match.exists())
        else:
            query = query.where(category_match.exists())
    position = filters.cursor_position()
    if position is not None:
        position_date, position_id = position
        query = query.where(
            or_(
                occurrence.transaction_date < position_date,
                and_(
                    occurrence.transaction_date == position_date,
                    occurrence.id < position_id,
                ),
            )
        )
    page = (
        query.order_by(occurrence.transaction_date.desc(), occurrence.id.desc())
        .limit(filters.page_size + 1)
        .cte("page")
    )
    history = select(literal(1)).select_from(occurrence).correlate(None).exists()
    anchor = select(literal(1)).subquery()
    summaries = [
        select(func.array_agg(aggregate_order_by(field.distinct(), field)))
        .select_from(linked)
        .where(
            occurrence_observation.c.occurrence_id == occurrence.id,
            field.is_not(None),
        )
        .correlate(occurrence)
        .scalar_subquery()
        for field in (observation.operation, observation.details)
    ]
    statement = (
        select(occurrence, history.label("history_exists"), summaries[0], summaries[1])
        .select_from(
            anchor.outerjoin(page, true()).outerjoin(
                occurrence, occurrence.id == page.c.id
            )
        )
        .order_by(page.c.transaction_date.desc(), page.c.id.desc())
    )
    async with AsyncSession(engine) as session:
        rows = (await session.execute(statement)).all()
    history_exists = rows[0].history_exists
    # SQLAlchemy types ORM entities as non-null even on the nullable side of an outer join.
    items = [
        _item(
            occurrence,
            cast(list[str] | None, row[2]) or [],
            cast(list[str] | None, row[3]) or [],
        )
        for row in rows
        if (occurrence := cast(TransactionOccurrence | None, row[0])) is not None
    ]
    has_next = len(items) > filters.page_size
    items = items[: filters.page_size]
    next_cursor = None
    if has_next:
        last = items[-1]
        next_cursor = filters.encode_cursor(last.date, int(last.id))
    return TransactionPage(
        items=items,
        next_cursor=next_cursor,
        history_exists=history_exists,
    )


async def detail(engine: AsyncEngine, occurrence_id: int) -> TransactionDetail | None:
    """Return the occurrence and only its explicitly linked source observations."""
    statement = (
        select(
            TransactionOccurrence,
            TransactionObservation,
            TransactionClassification,
            TransactionContext,
        )
        .select_from(TransactionOccurrence)
        .outerjoin(
            occurrence_observation,
            occurrence_observation.c.occurrence_id == TransactionOccurrence.id,
        )
        .outerjoin(
            TransactionObservation,
            occurrence_observation.c.observation_id == TransactionObservation.id,
        )
        .outerjoin(
            TransactionClassification,
            TransactionClassification.occurrence_id == TransactionOccurrence.id,
        )
        .outerjoin(
            TransactionContext,
            TransactionContext.occurrence_id == TransactionOccurrence.id,
        )
        .where(TransactionOccurrence.id == occurrence_id)
        .order_by(TransactionObservation.id)
    )
    async with AsyncSession(engine) as session:
        rows = (await session.execute(statement)).all()
    if not rows:
        return None
    possible_observations = (
        cast(TransactionObservation | None, row[1]) for row in rows
    )
    observations = [
        Observation(
            operation=observation.operation,
            details=observation.details,
            category=observation.category,
            booking_status=observation.booking_status,
        )
        for observation in {
            observation.id: observation
            for observation in possible_observations
            if observation is not None
        }.values()
    ]
    classifications = {
        classification.dimension: classification
        for row in rows
        if (classification := cast(TransactionClassification | None, row[2]))
        is not None
    }
    return TransactionDetail(
        **_item(
            rows[0][0],
            sorted(
                {
                    source.operation
                    for source in observations
                    if source.operation is not None
                }
            ),
            sorted(
                {
                    source.details
                    for source in observations
                    if source.details is not None
                }
            ),
        ).model_dump(),
        observations=observations,
        enrichment=build_result(
            list(classifications.values()), cast(TransactionContext | None, rows[0][3])
        ),
    )


async def categories(engine: AsyncEngine) -> list[str]:
    """Return distinct bank categories linked to existing occurrences."""
    statement = (
        select(TransactionObservation.category)
        .join(
            occurrence_observation,
            occurrence_observation.c.observation_id == TransactionObservation.id,
        )
        .join(
            TransactionOccurrence,
            TransactionOccurrence.id == occurrence_observation.c.occurrence_id,
        )
        .where(TransactionObservation.category.is_not(None))
        .distinct()
        .order_by(TransactionObservation.category)
    )
    async with AsyncSession(engine) as session:
        values = (await session.execute(statement)).scalars().all()
    return [value for value in values if value is not None]
