from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from personal_financial_assistant.infrastructure import database
from personal_financial_assistant.infrastructure.settings import Settings


@pytest.mark.asyncio
async def test_engine_is_disposed_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+asyncpg://user:password@localhost/db")
    )
    engine = database.create_engine(settings)
    dispose = AsyncMock()
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)

    def create_test_engine(_settings: Settings) -> AsyncEngine:
        return engine

    monkeypatch.setattr(database, "create_engine", create_test_engine)

    with pytest.raises(RuntimeError, match="failure"):
        async with database.engine_scope(settings) as opened:
            assert isinstance(opened, AsyncEngine)
            raise RuntimeError("failure")
    dispose.assert_awaited_once()
