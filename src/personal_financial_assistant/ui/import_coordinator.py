"""Own UI imports and their durable, non-sensitive outcomes."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID, uuid4

from asyncpg import InterfaceError, PostgresError
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker
from sqlalchemy.orm import aliased

from personal_financial_assistant.infrastructure.database import (
    PinnedConnectionBusy,
    PinnedConnectionLost,
)
from personal_financial_assistant.infrastructure.models import UIImportRun
from personal_financial_assistant.ingestion.service import (
    AccountMismatch,
    ImportInProgress,
    ImportResult,
    IngestionError,
    InvalidWorkbook,
    ingest_xlsx,
)
from personal_financial_assistant.ingestion.worker_client import (
    WorkbookWorker,
    WorkerCleanupError,
    WorkerTimeout,
    WorkerUnavailable,
)
from personal_financial_assistant.ingestion.xlsx_reader import WorkbookError

logger = logging.getLogger(__name__)
LOCK_KEY = 7718258
SHUTDOWN_GRACE = 5.0
LOCK_CHECK_INTERVAL = 2.0


class ImportConflict(Exception):
    """Another import is already running."""


class ImportRequestClosed(Exception):
    """The request ID already has a durable record and cannot be started again."""


class CoordinatorUnavailable(Exception):
    """Ownership or storage cannot be established safely."""


class ImportNotStarted(CoordinatorUnavailable):
    """The request was rejected before a run could be recorded."""


class ImportCoordinator:
    """Own at most one task and the database connection holding its UI lock."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._gate = asyncio.Lock()
        self._connection: AsyncConnection | None = None
        self._backend_pid: int | None = None
        self._task: asyncio.Task[None] | None = None
        self._monitor: asyncio.Task[None] | None = None
        self._maintenance: asyncio.Task[None] | None = None
        self._loss_cleanup: asyncio.Task[None] | None = None
        self._pending_starts: set[asyncio.Task[UUID]] = set()
        self._blocked = False
        self._closing = False

    async def open(self) -> None:
        """Acquire exclusive ownership and recover interrupted runs."""
        async with self._gate:
            await self._acquire()

    def maintain(self) -> None:
        """Retry ownership acquisition in the background when storage recovers."""
        if self._maintenance is None:
            self._maintenance = asyncio.create_task(self._maintain())
            self._maintenance.add_done_callback(self._monitor_done)

    async def _maintain(self) -> None:
        reported = False
        while not self._closing:
            if self._connection is None and not self._blocked:
                try:
                    await self.open()
                except CoordinatorUnavailable:
                    if not reported:
                        logger.warning("Import ownership is unavailable; retrying.")
                        reported = True
                else:
                    if reported:
                        logger.info("Import ownership recovered.")
                    reported = False
            await asyncio.sleep(LOCK_CHECK_INTERVAL)

    async def _acquire(self) -> None:
        if self._closing or self._blocked:
            raise CoordinatorUnavailable
        if self._connection is not None:
            if self._connection.closed or self._connection.invalidated:
                self._blocked = True
                raise CoordinatorUnavailable
            return
        connection: AsyncConnection | None = None
        try:
            connection = await self._engine.connect()
            acquired = await connection.scalar(
                select(func.pg_try_advisory_lock(LOCK_KEY))
            )
            if not acquired:
                await connection.rollback()
                await connection.close()
                raise CoordinatorUnavailable
            pid = await connection.scalar(select(func.pg_backend_pid()))
            if pid is None:
                raise CoordinatorUnavailable
            await connection.execute(
                update(UIImportRun)
                .where(UIImportRun.state == "running")
                .values(state="unknown", finished_at=func.now())
            )
            await connection.commit()
        except asyncio.CancelledError:
            if connection is not None and not connection.closed:
                await connection.invalidate()
                await connection.close()
            raise
        except CoordinatorUnavailable:
            if connection is not None and not connection.closed:
                await connection.invalidate()
                await connection.close()
            raise
        except SQLAlchemyError, PostgresError, InterfaceError, OSError, TimeoutError:
            if connection is not None:
                await connection.invalidate()
                await connection.close()
            raise CoordinatorUnavailable from None
        self._connection = connection
        self._backend_pid = pid
        self._monitor = asyncio.create_task(self._watch_lock())
        self._monitor.add_done_callback(self._monitor_done)

    async def start(self, directory: Path, *, run_id: UUID | None = None) -> UUID:
        """Persist a running row before scheduling the owned import."""
        task = asyncio.create_task(self._start(directory, run_id or uuid4()))
        self._pending_starts.add(task)
        task.add_done_callback(self._start_done)
        return await asyncio.shield(task)

    def _start_done(self, task: asyncio.Task[UUID]) -> None:
        self._pending_starts.discard(task)
        if task.cancelled():
            self._blocked = True
        else:
            error = task.exception()
            if error is not None and not isinstance(
                error, (ImportConflict, ImportRequestClosed, CoordinatorUnavailable)
            ):
                self._blocked = True
                logger.error("Import start failed unexpectedly.")

    async def _start(self, directory: Path, run_id: UUID) -> UUID:
        async with self._gate:
            if self._task is not None and not self._task.done():
                raise ImportConflict
            try:
                await self._acquire()
            except CoordinatorUnavailable:
                raise ImportNotStarted from None
            connection = self._connection
            if connection is None:
                raise ImportNotStarted
            try:
                inserted = await connection.execute(
                    insert(UIImportRun)
                    .values(id=run_id, state="running")
                    .on_conflict_do_nothing(index_elements=[UIImportRun.id])
                )
                await connection.commit()
            except (
                SQLAlchemyError,
                PostgresError,
                InterfaceError,
                OSError,
                TimeoutError,
            ):
                self._blocked = True
                await connection.invalidate()
                raise CoordinatorUnavailable from None
            if inserted.rowcount != 1:
                raise ImportRequestClosed
            if self._blocked:
                raise CoordinatorUnavailable
            self._task = asyncio.create_task(self._run(run_id, directory, connection))
            self._task.add_done_callback(self._import_done)
            return run_id

    async def resolve(self, run_id: UUID) -> UUID:
        """Close an unrecorded request ID without starting or overwriting a run."""
        task = asyncio.create_task(self._resolve(run_id))
        self._pending_starts.add(task)
        task.add_done_callback(self._start_done)
        return await asyncio.shield(task)

    async def _resolve(self, run_id: UUID) -> UUID:
        async with self._gate:
            await self._acquire()
            if self._task is not None and not self._task.done():
                raise ImportConflict
            connection = self._connection
            if connection is None:
                raise CoordinatorUnavailable
            try:
                await connection.execute(
                    insert(UIImportRun)
                    .values(id=run_id, state="unknown", finished_at=func.now())
                    .on_conflict_do_nothing(index_elements=[UIImportRun.id])
                )
                await connection.commit()
            except (
                SQLAlchemyError,
                PostgresError,
                InterfaceError,
                OSError,
                TimeoutError,
            ):
                self._blocked = True
                await connection.invalidate()
                raise CoordinatorUnavailable from None
            return run_id

    async def current(self) -> UIImportRun | None:
        """Read the latest durable run without changing state."""
        if self._blocked or self._pending_starts:
            raise CoordinatorUnavailable
        factory = async_sessionmaker(self._engine, expire_on_commit=False)
        try:
            async with factory() as session:
                return await session.scalar(
                    select(UIImportRun)
                    .order_by(UIImportRun.started_at.desc(), UIImportRun.id.desc())
                    .limit(1)
                )
        except SQLAlchemyError, PostgresError, InterfaceError, OSError, TimeoutError:
            raise CoordinatorUnavailable from None

    async def status(
        self, run_id: UUID
    ) -> tuple[UIImportRun | None, UIImportRun | None]:
        """Read a requested run and the latest run in the same database snapshot."""
        if self._blocked or self._pending_starts:
            raise CoordinatorUnavailable
        latest = aliased(UIImportRun)
        latest_id = (
            select(latest.id)
            .order_by(latest.started_at.desc(), latest.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            select(UIImportRun)
            .where(or_(UIImportRun.id == run_id, UIImportRun.id == latest_id))
            .order_by(UIImportRun.started_at.desc(), UIImportRun.id.desc())
        )
        factory = async_sessionmaker(self._engine, expire_on_commit=False)
        try:
            async with factory() as session:
                runs = (await session.scalars(statement)).all()
                tracked = next((run for run in runs if run.id == run_id), None)
                return tracked, runs[0] if runs else None
        except SQLAlchemyError, PostgresError, InterfaceError, OSError, TimeoutError:
            raise CoordinatorUnavailable from None

    async def _persist(
        self,
        connection: AsyncConnection,
        run_id: UUID,
        state: str,
        *,
        result: ImportResult | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if self._blocked or connection.closed or connection.invalidated:
            raise CoordinatorUnavailable
        values: dict[str, object] = {
            "state": state,
            "finished_at": func.now(),
            "error_code": error_code,
            "error_message": error_message,
        }
        if result is not None:
            for name in (
                "files_seen",
                "files_processed",
                "files_unchanged",
                "rows_read",
                "transactions_added",
                "transactions_updated",
                "observations_unchanged",
                "unresolved_observations",
            ):
                values[name] = getattr(result, name)
        updated = await connection.execute(
            update(UIImportRun)
            .where(UIImportRun.id == run_id, UIImportRun.state == "running")
            .values(**values)
        )
        if updated.rowcount != 1:
            await connection.rollback()
            raise CoordinatorUnavailable
        await connection.commit()

    async def _run(
        self, run_id: UUID, directory: Path, connection: AsyncConnection
    ) -> None:
        worker = WorkbookWorker()
        result: ImportResult | None = None
        state = "unknown"
        error_code: str | None = None
        error_message: str | None = None
        cancelled = False
        try:
            try:
                result = await ingest_xlsx(directory, connection, worker=worker)
                state = "no_files" if result.files_seen == 0 else "succeeded"
            except asyncio.CancelledError:
                cancelled = True
            except WorkerCleanupError:
                self._blocked = True
            except WorkerTimeout:
                state, error_code, error_message = (
                    "failed",
                    "workbook_timeout",
                    "The workbook operation timed out.",
                )
            except ImportInProgress:
                state, error_code, error_message = (
                    "failed",
                    "import_conflict",
                    "Another import is in progress. Wait for it to finish and retry.",
                )
            except AccountMismatch:
                state, error_code, error_message = (
                    "failed",
                    "account_mismatch",
                    "Export accounts do not match. Check the selected account and files.",
                )
            except InvalidWorkbook:
                state, error_code, error_message = (
                    "failed",
                    "invalid_workbook",
                    "An export is invalid, unreadable, or changed. Check the files and retry.",
                )
            except WorkbookError as exc:
                if str(exc) == "unable to read input directory":
                    state, error_code, error_message = (
                        "failed",
                        "folder_unavailable",
                        "The folder is unavailable. Check its location and permissions.",
                    )
                else:
                    state, error_code, error_message = (
                        "failed",
                        "invalid_workbook",
                        "An export is invalid, unreadable, or changed. Check the files and retry.",
                    )
            except WorkerUnavailable:
                state, error_code, error_message = (
                    "failed",
                    "worker_unavailable",
                    "The workbook reader is unavailable. Restart the application and retry.",
                )
            except IngestionError:
                state, error_code, error_message = (
                    "failed",
                    "import_failed",
                    "The import could not be completed.",
                )
            except (
                SQLAlchemyError,
                PostgresError,
                InterfaceError,
                PinnedConnectionLost,
                PinnedConnectionBusy,
                OSError,
                TimeoutError,
            ):
                self._blocked = True
        finally:
            try:
                await worker.close()
            except asyncio.CancelledError:
                self._blocked = True
                raise
            except WorkerCleanupError:
                self._blocked = True
                state, result, error_code, error_message = "unknown", None, None, None
            if not worker.reaped:
                self._blocked = True
                state, result, error_code, error_message = "unknown", None, None, None
        if not self._blocked:
            try:
                await self._persist(
                    connection,
                    run_id,
                    state,
                    result=result,
                    error_code=error_code,
                    error_message=error_message,
                )
            except (
                CoordinatorUnavailable,
                SQLAlchemyError,
                PostgresError,
                InterfaceError,
                OSError,
                TimeoutError,
            ):
                self._blocked = True
                logger.error("Import outcome could not be recorded.")
        if cancelled:
            raise asyncio.CancelledError

    def _import_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled() and not self._closing:
            self._blocked = True
        elif not task.cancelled() and task.exception() is not None:
            self._blocked = True
            logger.error("Import coordinator task failed.")

    async def _watch_lock(self) -> None:
        while not self._closing:
            await asyncio.sleep(LOCK_CHECK_INTERVAL)
            pid = self._backend_pid
            if pid is None:
                return
            try:
                async with self._engine.connect() as observer:
                    held = await observer.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks "
                            "WHERE locktype = 'advisory' AND pid = :pid "
                            "AND classid = 0 AND objid = :key AND objsubid = 1 "
                            "AND granted)"
                        ),
                        {"pid": pid, "key": LOCK_KEY},
                    )
            except (
                SQLAlchemyError,
                PostgresError,
                InterfaceError,
                OSError,
                TimeoutError,
            ):
                held = False
            if not held:
                await self._lose_ownership()
                return

    async def _lose_ownership(self) -> None:
        self._blocked = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.wait({self._task})
        if self._connection is not None:
            try:
                await self._connection.invalidate()
            except SQLAlchemyError, PostgresError, InterfaceError, OSError:
                logger.error("Import ownership could not be released.")

    def _monitor_done(self, task: asyncio.Task[None]) -> None:
        if not self._closing and (task.cancelled() or task.exception() is not None):
            self._blocked = True
            logger.error("Import ownership monitoring failed.")
            self._loss_cleanup = asyncio.create_task(self._lose_ownership())

    async def close(self) -> None:
        """Stop the owned import and release its session lock."""
        self._closing = True
        if self._maintenance is not None:
            self._maintenance.cancel()
            await asyncio.wait({self._maintenance})
        if self._pending_starts:
            await asyncio.wait(self._pending_starts)
        if self._monitor is not None:
            self._monitor.cancel()
            await asyncio.wait({self._monitor})
        if self._loss_cleanup is not None:
            await asyncio.wait({self._loss_cleanup})
            if (
                not self._loss_cleanup.cancelled()
                and self._loss_cleanup.exception() is not None
            ):
                logger.error("Import ownership cleanup failed.")
        task = self._task
        if task is not None and not task.done():
            done, _ = await asyncio.wait({task}, timeout=SHUTDOWN_GRACE)
            if not done:
                task.cancel()
                await asyncio.wait({task})
        connection = self._connection
        if connection is not None:
            try:
                if not connection.closed and not connection.invalidated:
                    if connection.in_transaction():
                        await connection.rollback()
                    await connection.scalar(select(func.pg_advisory_unlock(LOCK_KEY)))
                    await connection.commit()
            except (
                SQLAlchemyError,
                PostgresError,
                InterfaceError,
                OSError,
                TimeoutError,
            ):
                await connection.invalidate()
                logger.error("Import ownership release failed.")
            finally:
                await connection.close()
