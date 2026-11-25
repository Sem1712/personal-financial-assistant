from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import Request
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from personal_financial_assistant.infrastructure.settings import Settings, SettingsError
from personal_financial_assistant.ui import app as ui_app


@pytest.mark.asyncio
async def test_local_stylesheets_and_license_preserve_security_headers() -> None:
    app = ui_app.create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8765",
    ) as client:
        page = await client.get("/")
        assert '<html lang="en" data-bs-theme="dark">' in page.text
        assert page.text.index("/static/bootstrap.min.css") < page.text.index(
            "/static/styles.css"
        )
        for name in ("bootstrap.min.css", "styles.css", "bootstrap.LICENSE.txt"):
            response = await client.get(f"/static/{name}")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["content-security-policy"] == (
                "default-src 'self'; object-src 'none'; base-uri 'none'; "
                "frame-ancestors 'none'"
            )
            assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_lifespan_owns_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(database_url=SecretStr("postgresql+asyncpg://localhost/test"))
    load = AsyncMock(return_value=settings)
    engine = AsyncMock(spec=AsyncEngine)
    create = Mock(return_value=engine)
    monkeypatch.setattr(ui_app, "load_settings", load)
    monkeypatch.setattr(ui_app, "create_engine", create)
    app = ui_app.create_app()

    async with app.router.lifespan_context(app):
        create.assert_called_once_with(settings)
        assert app.state.engine is engine
        engine.dispose.assert_not_awaited()

    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_settings_keeps_shell_available_and_storage_explicit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        ui_app, "load_settings", AsyncMock(side_effect=SettingsError("private-secret"))
    )
    app = ui_app.create_app()

    @app.get("/api/storage-probe")
    async def probe(request: Request) -> None:
        ui_app.get_engine(request)

    async with app.router.lifespan_context(app):
        assert app.state.engine is None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8765",
        ) as client:
            response = await client.get("/")
            assert response.status_code == 200
            token = response.text.split('name="pfa-token" content="')[1].split('"')[0]
            unavailable = await client.get(
                "/api/storage-probe", headers={"x-pfa-token": token}
            )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "storage_unavailable"
    assert "private-secret" not in caplog.text
