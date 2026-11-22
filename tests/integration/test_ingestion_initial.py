from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.cli import run
from personal_financial_assistant.infrastructure.models import (
    SelectedAccount,
    SourceFile,
    TransactionObservation,
    TransactionOccurrence,
    occurrence_observation,
)
from personal_financial_assistant.ingestion.service import ingest_xlsx
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


@pytest.mark.asyncio
async def test_empty_export_with_account_is_recorded(
    tmp_path: Path, migrated_url: str
) -> None:
    (tmp_path / "input.xlsx").write_bytes(
        workbook([["", "Conti e Carte:", "TEST"], HEADINGS])
    )
    engine = create_async_engine(migrated_url)
    try:
        result = await ingest_xlsx(tmp_path, engine)
        assert (result.files_processed, result.rows_read) == (1, 0)
        async with engine.connect() as connection:
            source = (await connection.execute(select(SourceFile.__table__))).one()
            account = (
                await connection.execute(select(SelectedAccount.__table__))
            ).one()
        assert source.account_id == account.id
        assert account.account_reference == "TEST"
        async with engine.begin() as connection:
            await connection.execute(update(SourceFile).values(account_id=None))
        repeat = await ingest_xlsx(tmp_path, engine)
        assert (repeat.files_processed, repeat.files_unchanged) == (0, 1)
        async with engine.connect() as connection:
            source = (await connection.execute(select(SourceFile.__table__))).one()
        assert source.account_id == account.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_exports_are_deduplicated_without_inventing_an_account(
    tmp_path: Path, migrated_url: str
) -> None:
    empty = workbook([HEADINGS])
    (tmp_path / "a.xlsx").write_bytes(empty)
    (tmp_path / "copy.xlsx").write_bytes(empty)
    engine = create_async_engine(migrated_url)
    try:
        result = await ingest_xlsx(tmp_path, engine)
        assert (result.files_processed, result.files_unchanged, result.rows_read) == (
            1,
            1,
            0,
        )
        result = await ingest_xlsx(tmp_path, engine)
        assert (result.files_processed, result.files_unchanged) == (0, 2)
        (tmp_path / "b.xlsx").write_bytes(
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
        (tmp_path / "c.xlsx").write_bytes(workbook([["Preamble"], HEADINGS]))
        result = await ingest_xlsx(tmp_path, engine)
        assert (result.files_processed, result.files_unchanged, result.rows_read) == (
            2,
            2,
            1,
        )
        async with engine.connect() as connection:
            files = (await connection.execute(select(SourceFile.__table__))).all()
            accounts = (
                await connection.execute(select(SelectedAccount.__table__))
            ).all()
        assert len(accounts) == 1
        assert len(files) == 3
        assert sum(item.account_id is None for item in files) == 2
        result = await ingest_xlsx(tmp_path, engine)
        assert (result.files_processed, result.files_unchanged) == (0, 4)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_initial_import_persists_all_rows(
    tmp_path: Path, migrated_url: str
) -> None:
    (tmp_path / "first.xlsx").write_bytes(
        workbook(
            [
                ["Synthetic export"],
                HEADINGS,
                [
                    "01/01/2020",
                    "Operation A",
                    "Detail",
                    "TEST",
                    "CONTABILIZZATO",
                    "Food",
                    "EUR",
                    -12.34,
                ],
                [
                    "01/01/2021",
                    "Operation B",
                    "",
                    "TEST",
                    "NON CONTABILIZZATO",
                    "",
                    "EUR",
                    3.01,
                ],
            ]
        )
    )
    (tmp_path / "second.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2022",
                    "Operation C",
                    "",
                    "TEST",
                    "CONTABILIZZATO",
                    "Travel",
                    "EUR",
                    -4.0,
                ],
            ]
        )
    )
    engine = create_async_engine(migrated_url)
    try:
        result = await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            observations = (
                await connection.execute(select(TransactionObservation.__table__))
            ).all()
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
            files = (await connection.execute(select(SourceFile.__table__))).all()
        assert len(files) == 2
        assert len(observations) == len(occurrences) == 3
        assert {item.amount_minor for item in observations} == {-1234, 301, -400}
        assert {item.booking_status for item in observations} == {"pending", "booked"}
        assert {item.category for item in observations} == {"Food", "Travel", None}
        assert result.unresolved_observations == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_initial_overlapping_snapshots_preserve_ambiguity(
    tmp_path: Path, migrated_url: str
) -> None:
    pending = [
        "01/01/2022",
        "Synthetic",
        "",
        "TEST",
        "NON CONTABILIZZATO",
        "",
        "EUR",
        -1.0,
    ]
    booked = [
        "01/01/2022",
        "Synthetic",
        "",
        "TEST",
        "CONTABILIZZATO",
        "",
        "EUR",
        -1.0,
    ]
    (tmp_path / "a.xlsx").write_bytes(workbook([HEADINGS, pending, pending]))
    (tmp_path / "b.xlsx").write_bytes(workbook([HEADINGS, booked]))
    engine = create_async_engine(migrated_url)
    try:
        result = await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
            observations = (
                await connection.execute(select(TransactionObservation.__table__))
            ).all()
            links = (await connection.execute(select(occurrence_observation))).all()
        assert len(observations) == 3
        assert len(occurrences) == 2
        assert {item.booking_status for item in occurrences} == {"pending"}
        assert len(links) == 2
        assert result.unresolved_observations == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cli_imports_synthetic_workbook(
    tmp_path: Path, migrated_url: str, capsys: pytest.CaptureFixture[str]
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
                    -1.0,
                ],
            ]
        )
    )
    assert await run(["ingest-xlsx", "--input-dir", str(tmp_path)]) == 0
    assert "transactions added: 1" in capsys.readouterr().out
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            assert (
                len(
                    (
                        await connection.execute(
                            select(TransactionOccurrence.__table__)
                        )
                    ).all()
                )
                == 1
            )
    finally:
        await engine.dispose()
