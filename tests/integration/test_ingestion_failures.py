import asyncio
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.cli import run
from personal_financial_assistant.infrastructure.database import (
    PinnedConnectionBusy,
    PinnedConnectionLost,
)
from personal_financial_assistant.infrastructure.models import (
    SourceFile,
    TransactionOccurrence,
)
from personal_financial_assistant.ingestion import service
from personal_financial_assistant.ingestion.service import IngestionError, ingest_xlsx
from personal_financial_assistant.ingestion.worker_client import (
    WorkbookWorker,
    WorkerTimeout,
)
from personal_financial_assistant.ingestion.xlsx_reader import (
    FileSnapshot,
    discover_workbooks,
    read_workbook,
)
from tests.fixtures.intesa_xlsx import HEADINGS, workbook
from tests.fixtures.ui import create_export


@pytest.mark.asyncio
async def test_ingestion_uses_pinned_connection_without_reconnecting(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            pid = await connection.scalar(select(func.pg_backend_pid()))
            await connection.commit()
            result = await ingest_xlsx(tmp_path, connection)
            assert result.transactions_added == 1
            assert await connection.scalar(select(func.pg_backend_pid())) == pid
            await connection.commit()
            await connection.invalidate()
            with pytest.raises(PinnedConnectionLost):
                await ingest_xlsx(tmp_path, connection)
            assert connection.invalidated
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_lost_pinned_connection_cannot_commit_import(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            pid = await connection.scalar(select(func.pg_backend_pid()))
            assert pid is not None
            await connection.commit()
            worker = AsyncMock(spec=WorkbookWorker)
            worker.discover.side_effect = discover_workbooks
            worker.read.side_effect = read_workbook

            async def lose_connection(_snapshots: Sequence[FileSnapshot]) -> None:
                async with engine.begin() as killer:
                    await killer.scalar(select(func.pg_terminate_backend(pid)))

            worker.verify.side_effect = lose_connection
            with pytest.raises(SQLAlchemyError):
                await ingest_xlsx(tmp_path, connection, worker=worker)
        async with engine.connect() as check:
            assert await check.scalar(select(func.count()).select_from(SourceFile)) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ui_worker_imports_with_pinned_postgresql_connection(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection, WorkbookWorker() as worker:
            result = await ingest_xlsx(tmp_path, connection, worker=worker)
            assert result.transactions_added == 1
            assert (
                await connection.scalar(select(TransactionOccurrence.amount_minor))
                == -1234
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingestion_rejects_an_existing_pinned_transaction(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            await connection.scalar(select(1))
            with pytest.raises(PinnedConnectionBusy):
                await ingest_xlsx(tmp_path, connection)
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ui_verification_timeout_rolls_back_pinned_import(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    worker = AsyncMock(spec=WorkbookWorker)
    worker.discover.side_effect = discover_workbooks
    worker.read.side_effect = read_workbook
    worker.verify.side_effect = WorkerTimeout("Workbook operation timed out.")
    try:
        async with engine.connect() as connection:
            with pytest.raises(WorkerTimeout):
                await ingest_xlsx(tmp_path, connection, worker=worker)
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_authentication_failure_is_sanitized(
    tmp_path: Path,
    migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "input.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2022",
                    "Synthetic",
                    "",
                    "TEST",
                    "CONTABILIZZATO",
                    "",
                    "EUR",
                    -5,
                ],
            ]
        )
    )
    invalid_url = make_url(migrated_url).set(password="incorrect-private-password")
    monkeypatch.setenv(
        "PFA_DATABASE_URL", invalid_url.render_as_string(hide_password=False)
    )
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 1
    output = capsys.readouterr().err
    assert "database or storage unavailable" in output
    assert "incorrect-private-password" not in output
    assert str(tmp_path) not in output


@pytest.mark.asyncio
async def test_mixed_invalid_files_roll_back(tmp_path: Path, migrated_url: str) -> None:
    (tmp_path / "a.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2022",
                    "Synthetic",
                    "",
                    "TEST",
                    "CONTABILIZZATO",
                    "",
                    "EUR",
                    -5,
                ],
            ]
        )
    )
    (tmp_path / "b.xlsx").write_bytes(b"bad")
    engine = create_async_engine(migrated_url)
    try:
        with pytest.raises(IngestionError, match="file 2"):
            await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_nontext_category_rejects_batch_without_persistence(
    tmp_path: Path, migrated_url: str
) -> None:
    valid = ["01/01/2022", "Synthetic", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    invalid = ["01/01/2022", "Synthetic", "", "TEST", "CONTABILIZZATO", 123, "EUR", -5]
    (tmp_path / "a.xlsx").write_bytes(workbook([HEADINGS, valid]))
    (tmp_path / "b.xlsx").write_bytes(workbook([HEADINGS, invalid]))
    engine = create_async_engine(migrated_url)
    try:
        with pytest.raises(
            IngestionError, match="file 2: .*descriptive field at row 2"
        ):
            await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_wrong_account_in_empty_preamble_fails_atomically(
    tmp_path: Path, migrated_url: str, existing: bool
) -> None:
    valid = ["01/01/2022", "Synthetic", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "a.xlsx").write_bytes(
        workbook([["", "Conti e Carte:", "TEST"], HEADINGS, valid])
    )
    engine = create_async_engine(migrated_url)
    try:
        if existing:
            await ingest_xlsx(tmp_path, engine)
        (tmp_path / "b.xlsx").write_bytes(
            workbook([["", "Conti e Carte:", "OTHER"], HEADINGS])
        )
        with pytest.raises(IngestionError, match="account") as exc:
            await ingest_xlsx(tmp_path, engine)
        assert "OTHER" not in str(exc.value) and "TEST" not in str(exc.value)
        async with engine.connect() as connection:
            assert await connection.scalar(
                select(func.count()).select_from(SourceFile)
            ) == int(existing)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_preamble_account_is_checked_against_existing_selection(
    tmp_path: Path, migrated_url: str
) -> None:
    valid = ["01/01/2022", "Synthetic", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    target = tmp_path / "input.xlsx"
    target.write_bytes(workbook([HEADINGS, valid]))
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        target.write_bytes(workbook([["", "Conti e Carte:", "OTHER"], HEADINGS]))
        with pytest.raises(IngestionError, match="account"):
            await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_note_shaped_interior_row_rejects_batch(
    tmp_path: Path, migrated_url: str
) -> None:
    valid = ["01/01/2022", "Synthetic", "", "TEST", "CONTABILIZZATO", "", "EUR", -5]
    (tmp_path / "input.xlsx").write_bytes(
        workbook([HEADINGS, valid, ["", "Nota: ambiguous"], valid])
    )
    engine = create_async_engine(migrated_url)
    try:
        with pytest.raises(IngestionError, match="required field at row 3"):
            await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_imports_are_safe(tmp_path: Path, migrated_url: str) -> None:
    (tmp_path / "a.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2022",
                    "Synthetic",
                    "",
                    "TEST",
                    "CONTABILIZZATO",
                    "",
                    "EUR",
                    -5,
                ],
            ]
        )
    )
    engine = create_async_engine(migrated_url)
    try:
        results = await asyncio.gather(
            ingest_xlsx(tmp_path, engine),
            ingest_xlsx(tmp_path, engine),
            return_exceptions=True,
        )
        assert any(not isinstance(result, BaseException) for result in results)
        assert all(
            not isinstance(result, BaseException) or isinstance(result, IngestionError)
            for result in results
        )
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_storage_failure_rolls_back(tmp_path: Path, migrated_url: str) -> None:
    (tmp_path / "a.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2022",
                    "Synthetic",
                    "",
                    "TEST",
                    "CONTABILIZZATO",
                    "",
                    "EUR",
                    -5,
                ],
            ]
        )
    )
    engine = create_async_engine(migrated_url)

    def fail_insert(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO transaction_observation"):
            raise SQLAlchemyError("synthetic storage failure")

    event.listen(engine.sync_engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(SQLAlchemyError):
            await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_input_change_before_commit_rolls_back(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.xlsx"
    target.write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2022",
                    "Synthetic",
                    "",
                    "TEST",
                    "CONTABILIZZATO",
                    "",
                    "EUR",
                    -5,
                ],
            ]
        )
    )
    check = service.check_snapshots

    async def change_then_check(snapshots: Sequence[FileSnapshot]) -> None:
        target.write_bytes(b"changed")
        await check(snapshots)

    monkeypatch.setattr(service, "check_snapshots", change_then_check)
    engine = create_async_engine(migrated_url)
    try:
        with pytest.raises(IngestionError, match="changed"):
            await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await engine.dispose()
