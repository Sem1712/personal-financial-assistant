"""Build the local browser application."""

import asyncio
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncEngine

from personal_financial_assistant.infrastructure.database import create_engine
from personal_financial_assistant.infrastructure.settings import (
    SettingsError,
    load_settings,
)

from .errors import StorageUnavailable, register_error_handlers
from .import_coordinator import ImportCoordinator
from .import_routes import router as import_router
from .security import LocalSecurity
from .transaction_routes import router as transaction_router

STATIC = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Own the shared engine for the lifetime of the UI process."""
    engine: AsyncEngine | None = None
    try:
        settings = await load_settings()
    except SettingsError:
        logger.warning("UI storage configuration is unavailable.")
    else:
        engine = create_engine(settings)
    app.state.engine = engine
    coordinator = ImportCoordinator(engine) if engine is not None else None
    app.state.coordinator = coordinator
    if coordinator is not None:
        coordinator.maintain()
    try:
        yield
    finally:
        if coordinator is not None:
            await coordinator.close()
        if engine is not None:
            await engine.dispose()


def get_engine(request: Request) -> AsyncEngine:
    """Return the shared engine or signal that storage is unavailable."""
    engine = cast(AsyncEngine | None, request.app.state.engine)
    if engine is None:
        raise StorageUnavailable
    return engine


def create_app() -> FastAPI:
    """Construct a local-only UI without connecting to storage at startup."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    token = secrets.token_urlsafe(32)
    app.add_middleware(LocalSecurity, token=token)
    register_error_handlers(app)
    app.include_router(import_router)
    app.include_router(transaction_router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = await asyncio.to_thread((STATIC / "index.html").read_text, "utf-8")
        return HTMLResponse(html.replace("__PFA_TOKEN__", token))

    return app
