"""Own the application's async database engine and sessions."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import Settings


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
async def session_scope(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Open one transaction, committing on success and rolling back on failure."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        yield session
