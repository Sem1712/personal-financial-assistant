from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from personal_financial_assistant.ingestion import service
from personal_financial_assistant.ingestion.service import IngestionError, ingest_xlsx
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


@pytest.mark.asyncio
async def test_invalid_workbook_fails_before_database_connection(
    tmp_path: Path,
) -> None:
    (tmp_path / "secret.xlsx").write_bytes(b"bad")
    engine = create_async_engine("postgresql+asyncpg://user:password@localhost/no-db")
    try:
        with pytest.raises(IngestionError, match="file 1") as error:
            await ingest_xlsx(tmp_path, engine)
        assert str(tmp_path) not in str(error.value)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_workbook_requires_storage_for_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "empty.xlsx").write_bytes(workbook([HEADINGS]))
    engine = create_async_engine("postgresql+asyncpg://user:password@localhost/no-db")

    @asynccontextmanager
    async def unavailable(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
        raise OSError("database unavailable")
        yield

    monkeypatch.setattr(service, "session_scope", unavailable)
    try:
        with pytest.raises(OSError, match="database unavailable"):
            await ingest_xlsx(tmp_path, engine)
    finally:
        await engine.dispose()
