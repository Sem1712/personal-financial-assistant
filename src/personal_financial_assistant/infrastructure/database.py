"""Own the application's async database engine and sessions."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import Settings


class PinnedConnectionLost(Exception):
    """A pinned connection cannot safely be reused."""


class PinnedConnectionBusy(Exception):
    """The owner must finish its transaction before starting a new one."""


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an engine; callers must dispose it after use."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        connect_args={"timeout": 10, "command_timeout": 60},
        hide_parameters=True,
    )


@asynccontextmanager
async def engine_scope(settings: Settings) -> AsyncGenerator[AsyncEngine]:
    """Dispose pooled connections when the owning workflow ends."""
    engine = create_engine(settings)
    try:
        yield engine
    finally:
        await engine.dispose()


@asynccontextmanager
async def session_scope(
    engine: AsyncEngine | AsyncConnection,
) -> AsyncGenerator[AsyncSession]:
    """Own a transaction; a pinned connection must be valid and outside a transaction."""
    if isinstance(engine, AsyncConnection) and (engine.closed or engine.invalidated):
        raise PinnedConnectionLost("Pinned database connection unavailable.")
    if isinstance(engine, AsyncConnection) and engine.in_transaction():
        raise PinnedConnectionBusy(
            "Pinned database connection has an active transaction."
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        yield session
