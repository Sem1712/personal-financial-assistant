from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from personal_financial_assistant.transactions import (
    EnrichmentResult,
    TransactionDetail,
)

pytest_plugins = ("tests.unit.ui.test_transaction_routes",)


@pytest.mark.asyncio
async def test_detail_provenance_and_context_are_additive(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enrichment = EnrichmentResult.model_validate(
        {
            "category": {
                "value": "<b>food</b>",
                "status": "provisional",
                "source": "ai",
                "confidence": "72.5",
            },
            "user_explanation": "user",
            "ai_explanation": "AI",
        }
    )
    result = TransactionDetail(
        id="1",
        date=date(2025, 1, 1),
        amount_minor="-100",
        currency="EUR",
        booking_status="booked",
        reconciliation_state="confirmed",
        ongoing_expense=False,
        operations=[],
        details=[],
        observations=[],
        enrichment=enrichment,
    )
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.detail",
        AsyncMock(return_value=result),
    )
    response = await client.post("/api/transactions/detail", json={"id": "1"})
    assert response.status_code == 200
    assert response.json()["enrichment"] == enrichment.model_dump()


@pytest.mark.asyncio
async def test_detail_storage_failure_is_not_unclassified(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.detail",
        AsyncMock(side_effect=SQLAlchemyError("secret")),
    )
    response = await client.post("/api/transactions/detail", json={"id": "1"})
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "enrichment" not in response.json()
