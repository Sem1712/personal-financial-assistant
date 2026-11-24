import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from personal_financial_assistant.ingestion.service import (
    AccountMismatch,
    ImportInProgress,
    ImportResult,
    IngestionError,
    InvalidWorkbook,
)
from personal_financial_assistant.ingestion.worker_client import (
    WorkbookWorker,
    WorkerCleanupError,
)
from personal_financial_assistant.ingestion.xlsx_reader import WorkbookError
from personal_financial_assistant.ui import import_coordinator as module
from personal_financial_assistant.ui.import_coordinator import (
    CoordinatorUnavailable,
    ImportConflict,
    ImportCoordinator,
    ImportNotStarted,
)


def storage() -> tuple[AsyncMock, AsyncMock]:
    engine = AsyncMock(spec=AsyncEngine)
    connection = AsyncMock(spec=AsyncConnection)
    engine.connect = AsyncMock(return_value=connection)
    connection.scalar.side_effect = [True, 123, True]
    connection.execute.return_value = MagicMock(rowcount=1)
    connection.closed = False
    connection.invalidated = False
    connection.in_transaction = Mock(return_value=False)
    return engine, connection


async def quiet_monitor(_coordinator: ImportCoordinator) -> None:
    await asyncio.Event().wait()


class ReapedWorker:
    reaped = True

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_unexpected_error_reaps_started_worker_and_blocks_new_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine, _connection = storage()
    closed = asyncio.Event()

    class ObservedWorker(WorkbookWorker):
        async def close(self) -> None:
            await super().close()
            closed.set()

    worker = ObservedWorker()

    async def ingest(
        directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        await worker.discover(directory)
        assert not worker.reaped
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(module, "WorkbookWorker", lambda: worker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)
        await asyncio.wait_for(closed.wait(), 5)
        await asyncio.sleep(0)
        assert worker.reaped
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
        assert "Import coordinator task failed." in caplog.text
    finally:
        await coordinator.close()
        await worker.close()


@pytest.mark.asyncio
async def test_unexpected_error_with_failed_cleanup_preserves_error_and_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine, _connection = storage()
    attempted = asyncio.Event()

    class UnreapedWorker:
        reaped = False

        async def close(self) -> None:
            attempted.set()
            raise WorkerCleanupError("cleanup failed")

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(module, "WorkbookWorker", UnreapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)
        await asyncio.wait_for(attempted.wait(), 5)
        await asyncio.sleep(0)
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
        assert "Import coordinator task failed." in caplog.text
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_unconfirmed_worker_cleanup_blocks_new_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _connection = storage()
    cleanup_attempted = asyncio.Event()

    class UnreapedWorker:
        reaped = False

        async def close(self) -> None:
            cleanup_attempted.set()
            raise WorkerCleanupError("private diagnostic")

    async def ingest(
        _directory: Path,
        _connection: AsyncConnection,
        *,
        worker: WorkbookWorker,
    ) -> ImportResult:
        return ImportResult(0, 0, 0, 0, 0, 0, 0, 0)

    monkeypatch.setattr(module, "WorkbookWorker", UnreapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)
        await asyncio.wait_for(cleanup_attempted.wait(), 1)
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.current()
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_storage_error_rejects_start_without_exposing_details(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    engine, _connection = storage()
    engine.connect.side_effect = OSError("private database details")
    coordinator = ImportCoordinator(engine)
    with pytest.raises(ImportNotStarted) as error:
        await coordinator.start(tmp_path)
    await coordinator.close()
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


@pytest.mark.asyncio
async def test_failed_run_record_commit_is_not_claimed_as_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, connection = storage()
    connection.commit.side_effect = [None, SQLAlchemyError("uncertain commit"), None]
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        with pytest.raises(CoordinatorUnavailable) as error:
            await coordinator.start(tmp_path)
        assert not isinstance(error.value, ImportNotStarted)
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_uncertain_resolution_commit_blocks_further_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, connection = storage()
    connection.commit.side_effect = [None, SQLAlchemyError("uncertain commit"), None]
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.resolve(uuid4())
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_one_owned_task_blocks_duplicate_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, connection = storage()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        entered.set()
        await release.wait()
        return ImportResult(0, 0, 0, 0, 0, 0, 0, 0)

    monkeypatch.setattr(module, "WorkbookWorker", ReapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(ImportConflict):
            await coordinator.start(tmp_path)
        release.set()

        async def committed() -> None:
            while connection.commit.await_count < 3:
                await asyncio.sleep(0)

        await asyncio.wait_for(committed(), 1)
    finally:
        release.set()
        await coordinator.close()


@pytest.mark.asyncio
async def test_failed_import_is_sanitized_before_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine, connection = storage()

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        raise IngestionError("private transaction details")

    monkeypatch.setattr(module, "WorkbookWorker", ReapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)

        async def committed() -> None:
            while connection.commit.await_count < 3:
                await asyncio.sleep(0)

        await asyncio.wait_for(committed(), 1)
        statement = connection.execute.await_args_list[-1].args[0]
        parameters = str(statement.compile().params)
        assert "import_failed" in parameters
        assert "private transaction details" not in parameters
        assert "private transaction details" not in caplog.text
    finally:
        await coordinator.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "code", "message"),
    [
        (
            WorkbookError("unable to read input directory"),
            "folder_unavailable",
            "folder",
        ),
        (InvalidWorkbook("private workbook contents"), "invalid_workbook", "export"),
        (AccountMismatch("private account"), "account_mismatch", "account"),
        (ImportInProgress("private details"), "import_conflict", "import"),
    ],
)
async def test_known_import_failures_have_safe_actionable_reasons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    code: str,
    message: str,
) -> None:
    engine, connection = storage()

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        raise failure

    monkeypatch.setattr(module, "WorkbookWorker", ReapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)

        async def committed() -> None:
            while connection.commit.await_count < 3:
                await asyncio.sleep(0)

        await asyncio.wait_for(committed(), 1)
        statement = connection.execute.await_args_list[-1].args[0]
        parameters = str(statement.compile().params)
        assert code in parameters
        assert message in parameters.lower()
        assert "private" not in parameters
        assert str(tmp_path) not in parameters
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_terminal_state_write_failure_blocks_new_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, connection = storage()
    connection.execute.side_effect = [
        MagicMock(rowcount=1),
        MagicMock(rowcount=1),
        SQLAlchemyError("private database details"),
    ]

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        return ImportResult(0, 0, 0, 0, 0, 0, 0, 0)

    monkeypatch.setattr(module, "WorkbookWorker", ReapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)

        async def failed_write() -> None:
            while connection.execute.await_count < 3:
                await asyncio.sleep(0)

        await asyncio.wait_for(failed_write(), 1)
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.current()
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_shutdown_cancels_import_and_records_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, connection = storage()
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return ImportResult(0, 0, 0, 0, 0, 0, 0, 0)

    monkeypatch.setattr(module, "SHUTDOWN_GRACE", 0.01)
    monkeypatch.setattr(module, "WorkbookWorker", ReapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", quiet_monitor)
    coordinator = ImportCoordinator(engine)
    await coordinator.start(tmp_path)
    await asyncio.wait_for(entered.wait(), 1)
    await coordinator.close()
    assert cancelled.is_set()
    statement = connection.execute.await_args_list[-1].args[0]
    assert statement.compile().params["state"] == "unknown"


@pytest.mark.asyncio
async def test_monitor_failure_cancels_work_and_invalidates_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine, connection = storage()
    entered = asyncio.Event()
    fail = asyncio.Event()
    cancelled = asyncio.Event()

    async def ingest(
        _directory: Path, _connection: AsyncConnection, *, worker: WorkbookWorker
    ) -> ImportResult:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return ImportResult(0, 0, 0, 0, 0, 0, 0, 0)

    async def monitor(_coordinator: ImportCoordinator) -> None:
        await fail.wait()
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(module, "WorkbookWorker", ReapedWorker)
    monkeypatch.setattr(module, "ingest_xlsx", ingest)
    monkeypatch.setattr(ImportCoordinator, "_watch_lock", monitor)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 1)
        fail.set()
        await asyncio.wait_for(cancelled.wait(), 1)

        async def invalidated() -> None:
            while not connection.invalidate.await_count:
                await asyncio.sleep(0)

        await asyncio.wait_for(invalidated(), 1)
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
        assert "private diagnostic" not in caplog.text
    finally:
        await coordinator.close()
