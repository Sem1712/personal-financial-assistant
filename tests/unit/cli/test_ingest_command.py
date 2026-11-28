from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from asyncpg import CannotConnectNowError, InvalidPasswordError
from sqlalchemy.exc import SQLAlchemyError

from personal_financial_assistant import cli
from personal_financial_assistant.cli import run
from personal_financial_assistant.ingestion.service import ImportResult
from personal_financial_assistant.rules.work import EvaluationSummary
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


@pytest.mark.asyncio
async def test_empty_folder_is_explicit_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 0
    assert "No eligible XLSX" in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["failed", "pending", "unknown"])
async def test_completed_import_warns_about_incomplete_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    (tmp_path / "input.xlsx").write_bytes(workbook([HEADINGS]))
    summary = EvaluationSummary(
        attempted=0 if kind == "pending" else 1,
        completed=0,
        failed=int(kind == "failed"),
        pending=int(kind == "pending"),
        unknown=int(kind == "unknown"),
        items=(),
    )
    result = ImportResult(1, 1, 0, 1, 1, 0, 0, 0, evaluation=summary)

    @asynccontextmanager
    async def engine_scope(_settings: object) -> AsyncGenerator[object]:
        yield object()

    monkeypatch.setattr(cli, "load_settings", AsyncMock(return_value=object()))
    monkeypatch.setattr(cli, "engine_scope", engine_scope)
    monkeypatch.setattr(cli, "ingest_xlsx", AsyncMock(return_value=result))
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 0
    output = capsys.readouterr()
    assert "transactions added: 1" in output.out
    assert "evaluation" in (output.out + output.err).lower()
    assert kind in (output.out + output.err).lower()
    assert str(tmp_path) not in output.out + output.err


@pytest.mark.asyncio
async def test_missing_settings_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "input.xlsx").write_bytes(workbook([HEADINGS]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PFA_DATABASE_URL", raising=False)
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) != 0
    captured = capsys.readouterr()
    assert "database_url" in captured.err
    assert str(tmp_path) not in captured.err


@pytest.mark.asyncio
async def test_database_errors_do_not_expose_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "input.xlsx").write_bytes(workbook([HEADINGS]))
    monkeypatch.setenv("PFA_DATABASE_URL", "postgresql+asyncpg://u:secret@localhost/db")

    async def fail(*args: object, **kwargs: object) -> ImportResult:
        raise SQLAlchemyError("secret private-account")

    monkeypatch.setattr(cli, "ingest_xlsx", fail)
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) != 0
    captured = capsys.readouterr()
    assert "database or storage unavailable" in captured.err
    assert "secret" not in captured.err and "private-account" not in captured.err


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [InvalidPasswordError, CannotConnectNowError])
async def test_driver_errors_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_type: type[Exception],
) -> None:
    (tmp_path / "input.xlsx").write_bytes(workbook([HEADINGS]))
    monkeypatch.setenv("PFA_DATABASE_URL", "postgresql+asyncpg://u:secret@localhost/db")

    async def fail(*args: object, **kwargs: object) -> ImportResult:
        raise error_type("secret private-account")

    monkeypatch.setattr(cli, "ingest_xlsx", fail)
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "database or storage unavailable" in captured.err
    assert "secret" not in captured.err and "private-account" not in captured.err
