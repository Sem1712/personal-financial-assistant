import asyncio
import random
import signal
import string
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from personal_financial_assistant.ingestion.worker_client import (
    WorkbookWorker,
    WorkerCleanupError,
    WorkerTimeout,
)
from personal_financial_assistant.ingestion.xlsx_reader import WorkbookError
from tests.fixtures.intesa_xlsx import HEADINGS, workbook
from tests.fixtures.ui import create_export


@pytest.mark.asyncio
async def test_worker_discovers_reads_and_checks_synthetic_workbook(
    tmp_path: Path,
) -> None:
    create_export(tmp_path)
    async with WorkbookWorker() as worker:
        snapshots = await worker.discover(tmp_path)
        assert len(snapshots) == 1
        parsed = await worker.read(snapshots[0])
        assert len(parsed.observations) == 1
        assert parsed.observations[0].amount_minor == -1234
        await worker.verify(snapshots)


@pytest.mark.asyncio
async def test_worker_transfers_values_larger_than_one_pipe_chunk(
    tmp_path: Path,
) -> None:
    value = "".join(random.Random(42).choices(string.ascii_letters, k=70000))
    (tmp_path / "synthetic.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                ["01/01/2025", value, "", "TEST", "CONTABILIZZATO", "", "EUR", -1],
            ]
        )
    )
    async with WorkbookWorker() as worker:
        snapshots = await worker.discover(tmp_path)
        parsed = await worker.read(snapshots[0])
    assert parsed.observations[0].operation == value


@pytest.mark.asyncio
async def test_worker_reports_changed_file_without_disclosing_path(
    tmp_path: Path,
) -> None:
    path = create_export(tmp_path)
    async with WorkbookWorker() as worker:
        snapshots = await worker.discover(tmp_path)
        path.write_bytes(b"changed")
        with pytest.raises(WorkbookError) as error:
            await worker.verify(snapshots)
        assert str(tmp_path) not in str(error.value)


@pytest.mark.asyncio
async def test_worker_receives_no_inherited_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PFA_DATABASE_URL", "private-credential")
    original = asyncio.create_subprocess_exec
    environments: list[dict[str, str]] = []

    async def start(
        *args: str,
        stdin: int,
        stdout: int,
        stderr: int,
        env: dict[str, str],
        close_fds: bool,
    ) -> asyncio.subprocess.Process:
        environments.append(env)
        return await original(
            *args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=env,
            close_fds=close_fds,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    async with WorkbookWorker() as worker:
        assert await worker.discover(tmp_path) == []
    assert environments == [{}]


@pytest.mark.asyncio
async def test_timeout_reaps_worker_and_prevents_reuse(tmp_path: Path) -> None:
    worker = WorkbookWorker(operation_timeout=0.000001)
    with pytest.raises(WorkerTimeout):
        await worker.discover(tmp_path)
    assert worker.reaped
    with pytest.raises(RuntimeError):
        await worker.discover(tmp_path)


@pytest.mark.asyncio
async def test_cancellation_reaps_the_running_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = asyncio.create_subprocess_exec
    started = asyncio.Event()

    async def start(
        *args: str,
        stdin: int,
        stdout: int,
        stderr: int,
        env: dict[str, str],
        close_fds: bool,
    ) -> asyncio.subprocess.Process:
        process = await original(
            sys.executable,
            "-c",
            "import time; time.sleep(3600)",
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=env,
            close_fds=close_fds,
        )
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    worker = WorkbookWorker()
    task = asyncio.create_task(worker.discover(tmp_path))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert worker.reaped


@pytest.mark.asyncio
async def test_cancellation_during_spawn_waits_for_and_reaps_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = asyncio.create_subprocess_exec
    spawning = asyncio.Event()
    allow_spawn = asyncio.Event()

    async def start(
        *args: str,
        stdin: int,
        stdout: int,
        stderr: int,
        env: dict[str, str],
        close_fds: bool,
    ) -> asyncio.subprocess.Process:
        spawning.set()
        await allow_spawn.wait()
        return await original(
            *args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=env,
            close_fds=close_fds,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    worker = WorkbookWorker()
    task = asyncio.create_task(worker.discover(tmp_path))
    await spawning.wait()
    task.cancel()
    await asyncio.sleep(0)
    try:
        assert not task.done()
    finally:
        allow_spawn.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert worker.reaped


@pytest.mark.asyncio
async def test_worker_that_ignores_termination_is_killed_and_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def start(
        *args: str,
        stdin: int,
        stdout: int,
        stderr: int,
        env: dict[str, str],
        close_fds: bool,
    ) -> asyncio.subprocess.Process:
        process = await original(
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(3600)",
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=env,
            close_fds=close_fds,
        )
        assert process.stdout is not None
        assert await process.stdout.readline() == b"ready\n"
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    worker = WorkbookWorker(operation_timeout=0.5, cleanup_timeout=0.05)
    with pytest.raises(WorkerTimeout):
        await worker.discover(tmp_path)
    assert worker.reaped
    assert children[0].returncode == -signal.SIGKILL


@pytest.mark.asyncio
async def test_unreaped_worker_blocks_further_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = WorkbookWorker(cleanup_timeout=0.001)
    process = AsyncMock(spec=asyncio.subprocess.Process)
    process.returncode = None
    process.terminate = Mock()
    process.kill = Mock()

    async def stuck() -> int:
        await asyncio.sleep(60)
        return 0

    process.wait.side_effect = stuck
    monkeypatch.setattr(worker, "_process", process)
    with pytest.raises(WorkerCleanupError):
        await worker.close()
    assert not worker.reaped
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    with pytest.raises(RuntimeError):
        await worker.discover(tmp_path)
