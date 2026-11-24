"""Own a credential-free subprocess for bounded UI workbook operations."""

import asyncio
import logging
import struct
import sys
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import ValidationError

from .ui_worker import CHUNK_SIZE, WorkerRequest, WorkerResponse
from .xlsx_reader import FileSnapshot, ParsedFile, WorkbookError

logger = logging.getLogger(__name__)


class WorkerUnavailable(Exception):
    """The workbook worker is unavailable."""


class WorkerTimeout(WorkerUnavailable):
    """A workbook operation exceeded its deadline."""


class WorkerCleanupError(WorkerUnavailable):
    """The workbook worker could not be confirmed reaped."""


class WorkbookWorker:
    """Own one worker; operations default to 60 seconds and cleanup to 5 seconds.

    Always close the worker, including after errors. Failed cleanup raises
    ``WorkerCleanupError`` and the caller must not start another import.
    """

    def __init__(
        self, *, operation_timeout: float = 60, cleanup_timeout: float = 5
    ) -> None:
        self._operation_timeout = operation_timeout
        self._cleanup_timeout = cleanup_timeout
        self._process: asyncio.subprocess.Process | None = None
        self._starting: asyncio.Task[asyncio.subprocess.Process] | None = None
        self._late_cleanup_scheduled = False
        self._closed = False
        self._lock = asyncio.Lock()

    @property
    def reaped(self) -> bool:
        return self._starting is None and (
            self._process is None or self._process.returncode is not None
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Stop the subprocess and confirm it has been reaped."""
        self._closed = True
        if self._starting is not None:
            starting = self._starting
            try:
                self._process = await asyncio.wait_for(
                    asyncio.shield(starting), self._cleanup_timeout
                )
            except TimeoutError:
                if not self._late_cleanup_scheduled:
                    starting.add_done_callback(self._cleanup_after_start)
                    self._late_cleanup_scheduled = True
                raise WorkerCleanupError("Workbook worker cleanup failed.") from None
            except OSError:
                self._starting = None
                return
            self._starting = None
        process = self._process
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), self._cleanup_timeout)
            return
        except TimeoutError:
            pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), self._cleanup_timeout)
        except TimeoutError:
            raise WorkerCleanupError("Workbook worker cleanup failed.") from None

    def _cleanup_after_start(
        self, starting: asyncio.Task[asyncio.subprocess.Process]
    ) -> None:
        if starting.cancelled() or starting.exception() is not None:
            self._starting = None
            return
        self._process = starting.result()
        self._starting = None
        task = asyncio.create_task(self.close())
        task.add_done_callback(self._report_late_cleanup)

    @staticmethod
    def _report_late_cleanup(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.error("Workbook worker cleanup failed.")

    async def _exchange(self, request: WorkerRequest) -> WorkerResponse:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise WorkerUnavailable("Workbook worker unavailable.")
        data = request.model_dump_json().encode()
        for offset in range(0, len(data), CHUNK_SIZE):
            part = data[offset : offset + CHUNK_SIZE]
            process.stdin.write(struct.pack("!I", len(part)))
            process.stdin.write(part)
            await process.stdin.drain()
        process.stdin.write(struct.pack("!I", 0))
        await process.stdin.drain()
        chunks: list[bytes] = []
        while True:
            header = await process.stdout.readexactly(4)
            length = struct.unpack("!I", header)[0]
            if length == 0:
                break
            if length > CHUNK_SIZE:
                raise WorkerUnavailable("Invalid workbook worker response.")
            chunks.append(await process.stdout.readexactly(length))
        try:
            return WorkerResponse.model_validate_json(b"".join(chunks))
        except ValidationError:
            raise WorkerUnavailable("Invalid workbook worker response.") from None

    async def _run(self, request: WorkerRequest) -> WorkerResponse:
        async with self._lock:
            if self._closed:
                raise RuntimeError("Workbook worker is closed.")
            deadline = asyncio.get_running_loop().time() + self._operation_timeout
            if self._process is None:
                self._starting = asyncio.create_task(
                    asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "personal_financial_assistant.ingestion.ui_worker",
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        env={},
                        close_fds=True,
                    )
                )
                try:
                    self._process = await asyncio.wait_for(
                        asyncio.shield(self._starting), self._operation_timeout
                    )
                except TimeoutError:
                    await self.close()
                    raise WorkerTimeout("Workbook operation timed out.") from None
                except asyncio.CancelledError:
                    await self.close()
                    raise
                except OSError:
                    self._starting = None
                    self._closed = True
                    raise WorkerUnavailable("Workbook worker unavailable.") from None
                self._starting = None
                if self._closed:
                    await self.close()
                    raise WorkerUnavailable("Workbook worker unavailable.")
            try:
                response = await asyncio.wait_for(
                    self._exchange(request),
                    max(0, deadline - asyncio.get_running_loop().time()),
                )
            except TimeoutError:
                await self.close()
                raise WorkerTimeout("Workbook operation timed out.") from None
            except asyncio.CancelledError:
                await self.close()
                raise
            except BrokenPipeError, ConnectionResetError, asyncio.IncompleteReadError:
                await self.close()
                raise WorkerUnavailable("Workbook worker unavailable.") from None
            except WorkerUnavailable:
                await self.close()
                raise
            if response.error is not None:
                raise WorkbookError(response.error)
            return response

    async def discover(self, directory: Path) -> list[FileSnapshot]:
        response = await self._run(
            WorkerRequest(operation="discover", directory=directory)
        )
        if response.snapshots is None:
            raise WorkerUnavailable("Invalid workbook worker response.")
        return response.snapshots

    async def read(self, snapshot: FileSnapshot) -> ParsedFile:
        response = await self._run(WorkerRequest(operation="read", snapshot=snapshot))
        if response.parsed is None:
            raise WorkerUnavailable("Invalid workbook worker response.")
        return response.parsed

    async def verify(self, snapshots: Sequence[FileSnapshot]) -> None:
        await self._run(WorkerRequest(operation="verify", snapshots=list(snapshots)))
