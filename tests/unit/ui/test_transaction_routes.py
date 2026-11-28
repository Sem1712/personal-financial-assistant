import re
from collections.abc import AsyncGenerator
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from personal_financial_assistant.transactions import EnrichmentResult
from personal_financial_assistant.transactions.service import (
    Observation,
    TransactionDetail,
    TransactionItem,
    TransactionPage,
)
from personal_financial_assistant.ui.app import create_app

ORIGIN = "http://127.0.0.1:8765"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    app = create_app()
    app.state.engine = MagicMock(spec=AsyncEngine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url=ORIGIN,
    ) as http:
        bootstrap = await http.get("/")
        match = re.search(r'<meta name="pfa-token" content="([^"]+)">', bootstrap.text)
        assert match is not None
        http.headers.update({"x-pfa-token": match.group(1), "origin": ORIGIN})
        yield http


@pytest.mark.asyncio
async def test_transaction_contracts(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = TransactionItem(
        id="9223372036854775807",
        date=date(2025, 1, 1),
        amount_minor="-9223372036854775808",
        currency="EUR",
        booking_status="unknown",
        reconciliation_state="unresolved",
        ongoing_expense=False,
        operations=["private"],
        details=["recorded detail"],
    )
    search = AsyncMock(
        return_value=TransactionPage(
            items=[item], next_cursor=None, history_exists=True
        )
    )
    detail = AsyncMock(
        return_value=TransactionDetail(
            **item.model_dump(),
            enrichment=EnrichmentResult(),
            observations=[
                Observation(
                    operation="private",
                    details=None,
                    category=None,
                    booking_status="booked",
                )
            ],
        )
    )
    categories = AsyncMock(return_value=["Bank suggestion"])
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.search", search
    )
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.detail", detail
    )
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.categories", categories
    )
    response = await client.post(
        "/api/transactions/search",
        json={"text": "private", "amount_min": "5.00", "direction": "withdrawals"},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["amount_minor"] == "-9223372036854775808"
    assert response.json()["items"][0]["id"] == "9223372036854775807"
    assert response.json()["items"][0]["operations"] == ["private"]
    assert response.json()["items"][0]["details"] == ["recorded detail"]
    assert "enrichment" not in response.json()["items"][0]
    assert "private" not in str(response.request.url)
    assert search.await_args is not None
    assert search.await_args.args[1].amount_min == 500
    assert search.await_args.args[1].direction == "withdrawals"
    assert search.await_args.args[1].page_size == 100
    response = await client.post("/api/transactions/detail", json={"id": item.id})
    assert response.json()["observations"][0]["operation"] == "private"
    assert response.json()["enrichment"]["category"] == {
        "value": None,
        "status": "unclassified",
        "source": None,
        "confidence": None,
    }
    assert item.id not in str(response.request.url)
    response = await client.post("/api/transactions/categories", json={})
    assert response.json() == {"categories": ["Bank suggestion"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/transactions/search", {"amount_min": "private invalid"}),
        ("/api/transactions/search", {"amount_min": "-0.01"}),
        ("/api/transactions/search", {"direction": "other"}),
        (
            "/api/transactions/search",
            {"date_from": "2025-02-01", "date_to": "2025-01-01"},
        ),
        ("/api/transactions/detail", {"id": "private invalid"}),
        ("/api/transactions/detail", {"id": "9223372036854775808"}),
    ],
)
async def test_invalid_inputs_are_sanitized(
    client: httpx.AsyncClient, path: str, body: dict[str, str]
) -> None:
    response = await client.post(path, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_missing_and_unavailable_are_explicit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.detail",
        AsyncMock(return_value=None),
    )
    response = await client.post("/api/transactions/detail", json={"id": "1"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    monkeypatch.setattr(
        "personal_financial_assistant.ui.transaction_routes.search",
        AsyncMock(side_effect=SQLAlchemyError("private")),
    )
    response = await client.post("/api/transactions/search", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert "private" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "path", "body"),
    [
        ("search", "/api/transactions/search", {}),
        ("detail", "/api/transactions/detail", {"id": "1"}),
        ("categories", "/api/transactions/categories", {}),
    ],
)
async def test_connection_errors_are_explicit(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    path: str,
    body: dict[str, str],
) -> None:
    monkeypatch.setattr(
        f"personal_financial_assistant.ui.transaction_routes.{name}",
        AsyncMock(side_effect=OSError("private connection details")),
    )
    response = await client.post(path, json=body)
    assert response.status_code == 503
    assert "private" not in response.text
