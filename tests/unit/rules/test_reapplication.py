from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from personal_financial_assistant.rules import work
from personal_financial_assistant.rules.types import (
    CategoryOverride,
    EvaluationResult,
    MerchantNoMatch,
    RuleValidationError,
)
from personal_financial_assistant.rules.work import validate_selection
from personal_financial_assistant.transactions import OccurrenceNotFound


@pytest.mark.parametrize(
    "ids", [(), (1, 1), (0,), (-1,), (True,), tuple(range(1, 502))]
)
def test_invalid_selections_are_rejected_before_writes(ids: tuple[int, ...]) -> None:
    with pytest.raises(RuleValidationError):
        validate_selection(ids)


def test_selection_preserves_requested_order() -> None:
    assert validate_selection((3, 1, 2)) == (3, 1, 2)


@pytest.mark.asyncio
async def test_reapplication_reports_individual_errors_and_preserves_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def transaction(
        _bind: object, *, occurrence_id: int
    ) -> AsyncGenerator[AsyncSession]:
        if occurrence_id == 2:
            raise OccurrenceNotFound
        yield AsyncMock(spec=AsyncSession)

    async def evaluate(_session: AsyncSession, occurrence_id: int) -> EvaluationResult:
        return EvaluationResult(
            occurrence_id,
            1,
            MerchantNoMatch(),
            CategoryOverride("personal", occurrence_id),
            (),
            (),
        )

    monkeypatch.setattr(work, "rules_transaction", transaction)
    monkeypatch.setattr(work, "evaluate_in_session", evaluate)
    result = await work.reapply_selected(AsyncMock(), [1, 2, 3])
    assert (result.completed, result.failed, result.unknown) == (2, 1, 0)
    assert [item.status for item in result.items] == [
        "completed",
        "not_found",
        "completed",
    ]
    assert result.items[0].result is not None
    assert result.items[0].result.category == CategoryOverride("personal", 1)
