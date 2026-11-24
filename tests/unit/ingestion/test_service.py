from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from personal_financial_assistant.ingestion import service
from personal_financial_assistant.ingestion.service import IngestionError, ingest_xlsx
from personal_financial_assistant.ingestion.worker_client import WorkbookWorker
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


@pytest.mark.asyncio
async def test_ui_worker_is_used_for_discovery_and_final_verification(
    tmp_path: Path,
) -> None:
    engine = create_async_engine("postgresql+asyncpg://user:password@localhost/no-db")
    try:
        worker = AsyncMock(spec=WorkbookWorker)
        worker.discover.return_value = []
        result = await ingest_xlsx(tmp_path, engine, worker=worker)
        worker.discover.assert_awaited_once_with(tmp_path)
        worker.verify.assert_awaited_once_with([])
        assert result.files_seen == 0
    finally:
        await engine.dispose()
