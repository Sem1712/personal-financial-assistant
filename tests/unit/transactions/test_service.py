from datetime import date
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import TransactionOccurrence
from personal_financial_assistant.transactions.filters import TransactionFilters
from personal_financial_assistant.transactions.service import categories, detail, search


class SearchRow(NamedTuple):
    occurrence: TransactionOccurrence | None
    history_exists: bool


@pytest.mark.asyncio
async def test_search_projects_distinct_occurrences_and_next_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock(spec=AsyncEngine)
    session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session
    monkeypatch.setattr(
        "personal_financial_assistant.transactions.service.AsyncSession",
        session_factory,
    )
    day = date(2025, 1, 1)
    first = TransactionOccurrence(
        id=2,
        transaction_date=day,
        amount_minor=-1,
        currency="EUR",
        booking_status="pending",
        reconciliation_state="pending-only",
    )
    second = TransactionOccurrence(
        id=1,
        transaction_date=day,
        amount_minor=-1,
        currency="EUR",
        booking_status="pending",
        reconciliation_state="pending-only",
    )
    result = MagicMock()
    result.all.return_value = [SearchRow(first, True), SearchRow(second, True)]
    session.execute.return_value = result
    filters = TransactionFilters.model_validate({"page_size": 1})
    page = await search(engine, filters)
    assert page.history_exists
    assert [item.id for item in page.items] == ["2"]
    assert page.items[0].amount_minor == "-1"
    assert page.items[0].ongoing_expense
    assert page.next_cursor is not None
    assert TransactionFilters.model_validate(
        {"cursor": page.next_cursor}
    ).cursor_position() == (
        day,
        2,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["search", "detail", "categories"])
async def test_storage_errors_are_not_reported_as_empty_results(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = MagicMock(spec=AsyncEngine)
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = SQLAlchemyError("database unavailable")
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session
    monkeypatch.setattr(
        "personal_financial_assistant.transactions.service.AsyncSession",
        session_factory,
    )
    with pytest.raises(SQLAlchemyError):
        if operation == "search":
            await search(engine, TransactionFilters())
        elif operation == "detail":
            await detail(engine, 1)
        else:
            await categories(engine)
