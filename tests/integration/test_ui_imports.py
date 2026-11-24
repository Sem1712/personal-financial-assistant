import asyncio
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from personal_financial_assistant.infrastructure.models import (
    SourceFile,
    UIImportRun,
)
from personal_financial_assistant.ingestion import service as ingestion_service
from personal_financial_assistant.ingestion.worker_client import (
    WorkbookWorker,
    WorkerTimeout,
)
from personal_financial_assistant.ingestion.xlsx_reader import FileSnapshot
from personal_financial_assistant.ui import import_coordinator as coordinator_module
from personal_financial_assistant.ui.app import create_app
from personal_financial_assistant.ui.import_coordinator import (
    CoordinatorUnavailable,
    ImportConflict,
    ImportCoordinator,
    ImportNotStarted,
    ImportRequestClosed,
)
from tests.fixtures.ui import create_export


async def finished(coordinator: ImportCoordinator) -> UIImportRun:
    async def poll() -> UIImportRun:
        while True:
            try:
                run = await coordinator.current()
            except CoordinatorUnavailable:
                await asyncio.sleep(0.02)
                continue
            if run is not None and run.state != "running":
                return run
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(poll(), 15)


@pytest.mark.asyncio
async def test_empty_valid_repeat_and_invalid_imports(
    tmp_path: Path, migrated_url: str
) -> None:
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.start(tmp_path)
        run = await finished(coordinator)
        assert run.state == "no_files"
        assert run.files_seen == 0

        create_export(tmp_path)
        await coordinator.start(tmp_path)
        run = await finished(coordinator)
        assert run.state == "succeeded"
        assert (run.files_seen, run.files_processed, run.transactions_added) == (
            1,
            1,
            1,
        )

        await coordinator.start(tmp_path)
        run = await finished(coordinator)
        assert run.state == "succeeded"
        assert (run.files_unchanged, run.transactions_added) == (1, 0)

        (tmp_path / "invalid.xlsx").write_bytes(b"invalid")
        await coordinator.start(tmp_path)
        run = await finished(coordinator)
        assert run.state == "failed"
        assert run.error_code == "invalid_workbook"
        assert run.error_message is not None
        assert str(tmp_path) not in run.error_message
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 1
            )
        await coordinator.start(tmp_path / "missing")
        run = await finished(coordinator)
        assert run.state == "failed"
        assert run.error_code == "folder_unavailable"
        assert run.error_message is not None
        assert str(tmp_path) not in run.error_message
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_status_finds_older_run_and_current_run(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    entered = asyncio.Event()
    release = asyncio.Event()
    discover = WorkbookWorker.discover

    async def stalled(worker: WorkbookWorker, directory: Path) -> list[FileSnapshot]:
        entered.set()
        await release.wait()
        return await discover(worker, directory)

    try:
        first_id = await coordinator.start(tmp_path)
        assert (await finished(coordinator)).id == first_id
        monkeypatch.setattr(WorkbookWorker, "discover", stalled)
        second_id = await coordinator.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 5)
        tracked, current = await coordinator.status(first_id)
        assert tracked is not None and tracked.id == first_id
        assert tracked.state == "no_files"
        assert current is not None and current.id == second_id
        assert current.state == "running"
        missing, current = await coordinator.status(uuid4())
        assert missing is None
        assert current is not None and current.id == second_id
        release.set()
        assert (await finished(coordinator)).id == second_id
    finally:
        release.set()
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolved_missing_request_cannot_start_after_restart(
    tmp_path: Path, migrated_url: str
) -> None:
    engine = create_async_engine(migrated_url)
    first = ImportCoordinator(engine)
    request_id = uuid4()
    try:
        await first.resolve(request_id)
        tracked, _ = await first.status(request_id)
        assert tracked is not None and tracked.state == "unknown"
    finally:
        await first.close()
    second = ImportCoordinator(engine)
    try:
        with pytest.raises(ImportRequestClosed):
            await second.start(tmp_path, run_id=request_id)
        tracked, _ = await second.status(request_id)
        assert tracked is not None and tracked.state == "unknown"
        await second.start(tmp_path)
        assert (await finished(second)).state == "no_files"
    finally:
        await second.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolution_http_closes_request_id(
    tmp_path: Path, migrated_url: str
) -> None:
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    app = create_app()
    app.state.coordinator = coordinator
    app.state.engine = engine
    origin = "http://127.0.0.1:8765"
    request_id = str(uuid4())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=origin
        ) as client:
            page = await client.get("/")
            token = re.search(r'<meta name="pfa-token" content="([^"]+)">', page.text)
            assert token is not None
            client.headers.update({"origin": origin, "x-pfa-token": token.group(1)})
            assert (
                await client.post("/api/imports/resolve", json={"id": request_id})
            ).json() == {"id": request_id}
            response = await client.post(
                "/api/imports",
                json={"input_dir": str(tmp_path), "request_id": request_id},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "import_request_closed"
            status = await client.post("/api/imports/status", json={"id": request_id})
            assert status.json()["run"]["state"] == "unknown"
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolution_blocks_a_delayed_start_before_it_reaches_the_gate(
    tmp_path: Path, migrated_url: str
) -> None:
    engine = create_async_engine(migrated_url)
    entered = asyncio.Event()
    release = asyncio.Event()

    class DelayedCoordinator(ImportCoordinator):
        async def _start(self, directory: Path, run_id: UUID) -> UUID:
            entered.set()
            await release.wait()
            return await super()._start(directory, run_id)

    coordinator = DelayedCoordinator(engine)
    request_id = uuid4()
    try:
        pending = asyncio.create_task(coordinator.start(tmp_path, run_id=request_id))
        await asyncio.wait_for(entered.wait(), 5)
        await coordinator.resolve(request_id)
        release.set()
        with pytest.raises(ImportRequestClosed):
            await pending
        tracked, _ = await coordinator.status(request_id)
        assert tracked is not None and tracked.state == "unknown"
    finally:
        release.set()
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolution_does_not_override_running_or_completed_import(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    entered = asyncio.Event()
    release = asyncio.Event()
    discover = WorkbookWorker.discover

    async def stalled(worker: WorkbookWorker, directory: Path) -> list[FileSnapshot]:
        entered.set()
        await release.wait()
        return await discover(worker, directory)

    monkeypatch.setattr(WorkbookWorker, "discover", stalled)
    try:
        run_id = await coordinator.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(ImportConflict):
            await coordinator.resolve(run_id)
        release.set()
        assert (await finished(coordinator)).state == "no_files"
        await coordinator.resolve(run_id)
        tracked, _ = await coordinator.status(run_id)
        assert tracked is not None and tracked.state == "no_files"
    finally:
        release.set()
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_competing_ingestion_reports_actionable_failure(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    try:
        async with engine.begin() as connection:
            await connection.execute(select(func.pg_advisory_xact_lock(7718257)))
            await coordinator.start(tmp_path)
            run = await finished(coordinator)
            assert run.state == "failed"
            assert run.error_code == "import_conflict"
            assert run.error_message is not None
            assert "another import" in run.error_message.lower()
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_imported_history_is_available_via_transaction_http(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    app = create_app()
    app.state.coordinator = coordinator
    app.state.engine = engine
    origin = "http://127.0.0.1:8765"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=origin
        ) as client:
            page = await client.get("/")
            token = re.search(r'<meta name="pfa-token" content="([^"]+)">', page.text)
            assert token is not None
            client.headers.update({"origin": origin, "x-pfa-token": token.group(1)})
            before = await client.post("/api/transactions/search", json={})
            assert before.json()["history_exists"] is False
            request_id = uuid4()
            started = await client.post(
                "/api/imports",
                json={"input_dir": str(tmp_path), "request_id": str(request_id)},
            )
            assert started.status_code == 202
            assert started.json()["id"] == str(request_id)
            run = await finished(coordinator)
            assert run.id == request_id
            assert run.state == "succeeded"
            after = await client.post(
                "/api/transactions/search",
                json={"text": "synthetic purchase", "amount_min": "-12.34"},
            )
            assert after.status_code == 200
            items = after.json()["items"]
            assert len(items) == 1
            assert items[0]["amount_minor"] == "-1234"
            observed = await client.post(
                "/api/transactions/detail", json={"id": items[0]["id"]}
            )
            assert observed.json()["observations"][0]["category"] == "Food"
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_running_import_blocks_same_and_other_owners(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(migrated_url)
    first = ImportCoordinator(engine)
    second = ImportCoordinator(engine)
    entered = asyncio.Event()
    release = asyncio.Event()
    discover = WorkbookWorker.discover

    async def wait_for_release(
        worker: WorkbookWorker, directory: Path
    ) -> list[FileSnapshot]:
        entered.set()
        await release.wait()
        return await discover(worker, directory)

    monkeypatch.setattr(WorkbookWorker, "discover", wait_for_release)
    try:
        await first.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(ImportConflict):
            await first.start(tmp_path)
        with pytest.raises(CoordinatorUnavailable):
            await second.start(tmp_path)
        with pytest.raises(CoordinatorUnavailable):
            await second.resolve(uuid4())
        run = await first.current()
        assert run is not None
        assert run.state == "running"
        release.set()
        assert (await finished(first)).state == "no_files"
    finally:
        release.set()
        await first.close()
        await second.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_lock_monitor_keeps_a_healthy_running_import(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(coordinator_module, "LOCK_CHECK_INTERVAL", 0.02)
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    entered = asyncio.Event()
    release = asyncio.Event()
    discover = WorkbookWorker.discover

    async def stalled(worker: WorkbookWorker, directory: Path) -> list[FileSnapshot]:
        entered.set()
        await release.wait()
        return await discover(worker, directory)

    monkeypatch.setattr(WorkbookWorker, "discover", stalled)
    try:
        await coordinator.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.sleep(0.15)
        run = await coordinator.current()
        assert run is not None
        assert run.state == "running"
        release.set()
        assert (await finished(coordinator)).state == "no_files"
    finally:
        release.set()
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_running_import_is_recovered_as_unknown(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    async with engine.begin() as connection:
        await connection.execute(
            insert(UIImportRun).values(
                id=uuid4(), state="running", started_at=func.now()
            )
        )
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.open()
        run = await coordinator.current()
        assert run is not None
        assert run.state == "unknown"
        assert run.finished_at is not None
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["discover", "read", "verify"])
async def test_workbook_timeout_does_not_commit(
    tmp_path: Path,
    migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    create_export(tmp_path)
    engine: AsyncEngine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)

    async def timeout(*_args: object) -> None:
        raise WorkerTimeout("Workbook operation timed out.")

    monkeypatch.setattr(WorkbookWorker, operation, timeout)
    try:
        await coordinator.start(tmp_path)
        run = await finished(coordinator)
        assert run.state == "failed"
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 0
            )
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_folder_requires_available_storage(tmp_path: Path) -> None:
    engine = create_async_engine("postgresql+asyncpg://localhost:1/unavailable")
    coordinator = ImportCoordinator(engine)
    try:
        with pytest.raises(ImportNotStarted):
            await coordinator.start(tmp_path)
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_lost_lock_cancels_import_and_allows_unknown_recovery(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(coordinator_module, "LOCK_CHECK_INTERVAL", 0.02)
    engine = create_async_engine(migrated_url)
    owner = ImportCoordinator(engine)
    successor = ImportCoordinator(engine)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def stalled(_worker: WorkbookWorker, _directory: Path) -> list[FileSnapshot]:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return []

    monkeypatch.setattr(WorkbookWorker, "discover", stalled)
    try:
        await owner.start(tmp_path)
        await asyncio.wait_for(entered.wait(), 5)
        async with engine.begin() as connection:
            pid = await connection.scalar(
                text(
                    "SELECT pid FROM pg_catalog.pg_locks WHERE locktype = 'advisory' "
                    "AND classid = 0 AND objid = :key AND objsubid = 1 AND granted"
                ),
                {"key": coordinator_module.LOCK_KEY},
            )
            assert pid is not None
            await connection.scalar(select(func.pg_terminate_backend(pid)))
        await asyncio.wait_for(cancelled.wait(), 5)
        await successor.open()
        run = await successor.current()
        assert run is not None
        assert run.state == "unknown"
        with pytest.raises(CoordinatorUnavailable):
            await owner.start(tmp_path)
    finally:
        await owner.close()
        await successor.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unrecorded_terminal_outcome_blocks_and_recovers_unknown(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)

    async def fail_persist(
        _self: ImportCoordinator, *_args: object, **_kwargs: object
    ) -> None:
        raise SQLAlchemyError("private details")

    monkeypatch.setattr(ImportCoordinator, "_persist", fail_persist)
    try:
        await coordinator.start(tmp_path)

        async def wait_until_indeterminate() -> None:
            while True:
                try:
                    await coordinator.current()
                except CoordinatorUnavailable:
                    return
                await asyncio.sleep(0.02)

        await asyncio.wait_for(wait_until_indeterminate(), 10)
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.start(tmp_path)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(select(func.count()).select_from(SourceFile))
                == 1
            )
    finally:
        await coordinator.close()
    successor = ImportCoordinator(engine)
    try:
        await successor.open()
        run = await successor.current()
        assert run is not None
        assert run.state == "unknown"
    finally:
        await successor.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingestion_commit_response_loss_recovers_as_unknown(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_export(tmp_path)
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    committed = asyncio.Event()
    session_scope = ingestion_service.session_scope

    @asynccontextmanager
    async def lose_commit_response(
        database: AsyncEngine | AsyncConnection,
    ) -> AsyncGenerator[AsyncSession]:
        async with session_scope(database) as session:
            yield session
        committed.set()
        raise SQLAlchemyError("simulated lost commit response")

    monkeypatch.setattr(ingestion_service, "session_scope", lose_commit_response)
    try:
        try:
            await coordinator.start(tmp_path)
            await asyncio.wait_for(committed.wait(), 10)

            async def wait_for_block() -> None:
                while True:
                    try:
                        await coordinator.current()
                    except CoordinatorUnavailable:
                        return
                    await asyncio.sleep(0.02)

            await asyncio.wait_for(wait_for_block(), 5)

            async def wait_for_unavailable_start() -> None:
                while True:
                    try:
                        await coordinator.start(tmp_path)
                    except ImportConflict:
                        await asyncio.sleep(0.02)
                    except CoordinatorUnavailable:
                        return
                    else:
                        pytest.fail(
                            "A new import was accepted after an uncertain commit."
                        )

            await asyncio.wait_for(wait_for_unavailable_start(), 5)
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(
                        select(func.count()).select_from(SourceFile)
                    )
                    == 1
                )
        finally:
            await coordinator.close()

        successor = ImportCoordinator(engine)
        try:
            await successor.open()
            run = await successor.current()
            assert run is not None
            assert run.state == "unknown"
            assert run.error_message is None
        finally:
            await successor.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_start_never_leaves_an_unowned_running_row(
    tmp_path: Path, migrated_url: str
) -> None:
    engine = create_async_engine(migrated_url)
    coordinator = ImportCoordinator(engine)
    try:
        await coordinator.open()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE FUNCTION delay_ui_run() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(0.3); "
                    "RETURN NEW; END $$"
                )
            )
            await connection.execute(
                text(
                    "CREATE TRIGGER delay_ui_run BEFORE INSERT ON ui_import_run "
                    "FOR EACH ROW EXECUTE FUNCTION delay_ui_run()"
                )
            )
        task = asyncio.create_task(coordinator.start(tmp_path))
        await asyncio.sleep(0.1)
        with pytest.raises(CoordinatorUnavailable):
            await coordinator.current()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        run = await asyncio.wait_for(finished(coordinator), 3)
        assert run.state == "no_files"
    finally:
        await coordinator.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_monitor_failure_cancels_import_and_fails_closed(
    tmp_path: Path, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(migrated_url)
    owner = ImportCoordinator(engine)
    successor = ImportCoordinator(engine)
    entered = asyncio.Event()
    fail_monitor = asyncio.Event()
    cancelled = asyncio.Event()

    async def monitor(_coordinator: ImportCoordinator) -> None:
        await fail_monitor.wait()
        raise RuntimeError("private diagnostic")

    async def stalled(_worker: WorkbookWorker, _directory: Path) -> list[FileSnapshot]:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return []

    try:
        with monkeypatch.context() as patches:
            patches.setattr(ImportCoordinator, "_watch_lock", monitor)
            patches.setattr(WorkbookWorker, "discover", stalled)
            await owner.start(tmp_path)
            await asyncio.wait_for(entered.wait(), 5)
            fail_monitor.set()
            await asyncio.wait_for(cancelled.wait(), 5)
            with pytest.raises(CoordinatorUnavailable):
                await owner.start(tmp_path)
            await owner.close()
        await successor.open()
        run = await successor.current()
        assert run is not None
        assert run.state == "unknown"
    finally:
        await owner.close()
        await successor.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_import_returns_persisted_counts_without_path(
    tmp_path: Path, migrated_url: str
) -> None:
    create_export(tmp_path)
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8765",
        ) as client,
    ):
        page = await client.get("/")
        token = re.search(r'<meta name="pfa-token" content="([^"]+)">', page.text)
        assert token is not None
        client.headers.update(
            {"x-pfa-token": token.group(1), "origin": "http://127.0.0.1:8765"}
        )
        response = await client.post("/api/imports", json={"input_dir": str(tmp_path)})
        assert response.status_code == 202
        assert str(tmp_path) not in response.text

        async def poll() -> dict[str, object]:
            while True:
                current = await client.get("/api/imports/current")
                assert current.status_code == 200
                assert str(tmp_path) not in current.text
                run: dict[str, object] = current.json()["run"]
                if run["state"] != "running":
                    return run
                await asyncio.sleep(0.02)

        run = await asyncio.wait_for(poll(), 15)
        assert run["state"] == "succeeded"
        assert isinstance(run["counts"], dict)
        assert run["counts"]["transactions_added"] == 1
