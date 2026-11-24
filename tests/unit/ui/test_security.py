import re
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pydantic import BaseModel

from personal_financial_assistant.ui.app import create_app

ORIGIN = "http://127.0.0.1:8765"


class Probe(BaseModel):
    count: int


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    @app.post("/api/probe")
    async def probe(value: Probe) -> dict[str, int]:
        return {"count": value.count}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as test_client:
        yield test_client


async def token(client: httpx.AsyncClient) -> str:
    response = await client.get("/")
    assert response.status_code == 200
    result = re.search(r'<meta name="pfa-token" content="([^"]+)">', response.text)
    assert result is not None
    return result.group(1)


@pytest.mark.asyncio
async def test_local_bootstrap_has_security_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert await token(client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {"host": "evil.example:8765"},
        {"host": "127.0.0.1:9999"},
        {"origin": "http://evil.example"},
    ],
)
async def test_invalid_host_and_origin_rejected(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    assert (await client.get("/", headers=headers)).status_code in (400, 403)


@pytest.mark.asyncio
async def test_api_requires_same_origin_token_and_json(
    client: httpx.AsyncClient,
) -> None:
    good = {
        "origin": ORIGIN,
        "x-pfa-token": await token(client),
        "sec-fetch-site": "same-origin",
    }
    assert (
        await client.post("/api/probe", headers=good, json={"count": 1})
    ).status_code == 200
    assert (
        await client.post("/api/probe", headers={"origin": ORIGIN}, json={})
    ).status_code == 403
    assert (
        await client.post(
            "/api/probe", headers={"x-pfa-token": good["x-pfa-token"]}, json={}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/probe", headers={**good, "origin": "http://evil.example"}, json={}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/probe", headers={**good, "sec-fetch-site": "cross-site"}, json={}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/probe",
            headers={**good, "content-type": "text/plain"},
            content="{}",
        )
    ).status_code in (403, 415)


@pytest.mark.asyncio
async def test_validation_errors_do_not_echo_sensitive_values(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "private-transaction-value"
    response = await client.post(
        "/api/probe",
        headers={"origin": ORIGIN, "x-pfa-token": await token(client)},
        json={"count": secret},
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_non_ascii_token_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/probe", headers=[(b"x-pfa-token", b"\xff")])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unexpected_error_is_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app()

    @app.get("/api/error")
    async def error() -> None:
        raise RuntimeError("private-transaction-value")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url=ORIGIN,
    ) as client:
        response = await client.get(
            "/api/error", headers={"x-pfa-token": await token(client)}
        )
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }
    assert response.headers["cache-control"] == "no-store"
    assert "private-transaction-value" not in response.text
    assert "private-transaction-value" not in caplog.text
    assert "Unexpected UI error" in caplog.text
