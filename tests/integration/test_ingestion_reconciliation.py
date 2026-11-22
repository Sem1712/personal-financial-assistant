import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.cli import run
from personal_financial_assistant.infrastructure.models import (
    SourceFile,
    TransactionObservation,
    TransactionOccurrence,
    occurrence_observation,
)
from personal_financial_assistant.ingestion.service import ingest_xlsx
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


def row(day: str, status: str, details: str = "") -> list[str | float]:
    return [day, "Synthetic", details, "TEST", status, "", "EUR", -5.0]


@pytest.mark.asyncio
async def test_repeat_and_pending_booking(tmp_path: Path, migrated_url: str) -> None:
    data = workbook([HEADINGS, row("01/01/2022", "NON CONTABILIZZATO")])
    (tmp_path / "first.xlsx").write_bytes(data)
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        (tmp_path / "copy.xlsx").write_bytes(data)
        for _ in range(5):
            result = await ingest_xlsx(tmp_path, engine)
            assert result.transactions_added == 0
        (tmp_path / "booked.xlsx").write_bytes(
            workbook([HEADINGS, row("01/01/2022", "CONTABILIZZATO", "changed")])
        )
        result = await ingest_xlsx(tmp_path, engine)
        assert result.transactions_updated == 1
        async with engine.connect() as connection:
            files = (await connection.execute(select(SourceFile.__table__))).all()
            observations = (
                await connection.execute(select(TransactionObservation.__table__))
            ).all()
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
        assert len(files) == len(observations) == 2
        assert [o.booking_status for o in occurrences] == ["booked"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cli_reports_repeated_import_counts(
    tmp_path: Path, migrated_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "secret.xlsx").write_bytes(
        workbook([HEADINGS, row("01/01/2022", "CONTABILIZZATO", "private")])
    )
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 0
    capsys.readouterr()
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "unchanged: 1" in output and "transactions added: 0" in output
    assert "observations unchanged: 1" in output and "transactions updated: 0" in output
    assert "private" not in output and str(tmp_path) not in output


@pytest.mark.asyncio
async def test_quickstart_console_command(tmp_path: Path, migrated_url: str) -> None:
    (tmp_path / "input.xlsx").write_bytes(
        workbook([HEADINGS, row("01/01/2022", "CONTABILIZZATO")])
    )

    async def invoke() -> tuple[int | None, str]:
        process = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "--locked",
            "personal-financial-assistant",
            "ingest-xlsx",
            "--input-dir",
            str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, (stdout + stderr).decode()

    status, output = await invoke()
    assert status == 0 and "transactions added: 1" in output
    status, output = await invoke()
    assert status == 0 and "transactions added: 0" in output
    (tmp_path / "bad.xlsx").write_bytes(b"bad")
    status, output = await invoke()
    assert status != 0 and "file 1" in output
    assert str(tmp_path) not in output
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
        assert len(occurrences) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ambiguous_and_changed_key(tmp_path: Path, migrated_url: str) -> None:
    pending = row("01/01/2022", "NON CONTABILIZZATO")
    (tmp_path / "a.xlsx").write_bytes(workbook([HEADINGS, pending, pending]))
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        (tmp_path / "b.xlsx").write_bytes(
            workbook(
                [
                    HEADINGS,
                    row("01/01/2022", "CONTABILIZZATO"),
                    row("02/01/2022", "CONTABILIZZATO"),
                ]
            )
        )
        result = await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
        assert sorted(o.booking_status for o in occurrences) == [
            "booked",
            "pending",
            "pending",
        ]
        assert result.unresolved_observations == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reordered_overlapping_exports_keep_duplicate_multiplicity(
    tmp_path: Path, migrated_url: str
) -> None:
    duplicate = row("01/01/2022", "CONTABILIZZATO")
    other = row("02/01/2022", "CONTABILIZZATO")
    (tmp_path / "a.xlsx").write_bytes(workbook([HEADINGS, duplicate, other, duplicate]))
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        (tmp_path / "b.xlsx").write_bytes(
            workbook([["Preamble"], HEADINGS, other, duplicate, duplicate])
        )
        result = await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
        assert len(occurrences) == 3
        assert result.transactions_added == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("old_status", ["CONTABILIZZATO", "NON CONTABILIZZATO"])
async def test_growth_preserves_status_and_leaves_new_rows_unlinked(
    tmp_path: Path, migrated_url: str, old_status: str
) -> None:
    (tmp_path / "a.xlsx").write_bytes(
        workbook([HEADINGS, row("01/01/2022", old_status)])
    )
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        (tmp_path / "b.xlsx").write_bytes(
            workbook(
                [
                    HEADINGS,
                    row("01/01/2022", "CONTABILIZZATO", "one"),
                    row("01/01/2022", "CONTABILIZZATO", "two"),
                ]
            )
        )
        result = await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
            observations = (
                await connection.execute(select(TransactionObservation.__table__))
            ).all()
            links = (await connection.execute(select(occurrence_observation))).all()
        assert [item.booking_status for item in occurrences] == [
            "booked" if old_status == "CONTABILIZZATO" else "pending",
            None,
        ]
        assert occurrences[1].reconciliation_state == "unresolved"
        assert [item.booking_status for item in observations] == [
            "booked" if old_status == "CONTABILIZZATO" else "pending",
            "booked",
            "booked",
        ]
        assert len(links) == 1
        assert result.unresolved_observations == 2
    finally:
        await engine.dispose()
