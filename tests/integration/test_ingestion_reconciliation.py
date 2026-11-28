import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.cli import run
from personal_financial_assistant.infrastructure.models import (
    SourceFile,
    TransactionObservation,
    TransactionOccurrence,
    occurrence_observation,
)
from personal_financial_assistant.ingestion.service import ingest_xlsx
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    detail,
    update_enrichment,
)
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


def row(day: str, status: str, details: str = "") -> list[str | float]:
    return [day, "Synthetic", details, "TEST", status, "", "EUR", -5.0]


@pytest.mark.asyncio
async def test_repeat_and_pending_booking(tmp_path: Path, migrated_url: str) -> None:
    pending = row("01/01/2022", "NON CONTABILIZZATO")
    pending[5] = "Bank pending"
    data = workbook([HEADINGS, pending])
    (tmp_path / "first.xlsx").write_bytes(data)
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as connection:
            occurrence_id = await connection.scalar(select(TransactionOccurrence.id))
        assert occurrence_id is not None
        await update_enrichment(
            engine,
            occurrence_id,
            EnrichmentUpdate.model_validate(
                {
                    "transaction_type": {
                        "value": "expense",
                        "status": "confirmed",
                        "source": "user",
                        "confidence": "99.25",
                    },
                    "category": {
                        "value": "groceries",
                        "status": "provisional",
                        "source": "ai",
                        "confidence": "72.50",
                    },
                    "budget_treatment": {
                        "value": "extraordinary",
                        "status": "confirmed",
                        "source": "rule",
                    },
                    "user_annotation": "synthetic note",
                    "user_explanation": "synthetic user explanation",
                    "ai_explanation": "synthetic AI explanation",
                }
            ),
        )
        initial = await detail(engine, occurrence_id)
        assert initial is not None
        expected_enrichment = initial.enrichment.model_dump()
        assert expected_enrichment == {
            "transaction_type": {
                "value": "expense",
                "status": "confirmed",
                "source": "user",
                "confidence": "99.25",
            },
            "category": {
                "value": "groceries",
                "status": "provisional",
                "source": "ai",
                "confidence": "72.50",
            },
            "budget_treatment": {
                "value": "extraordinary",
                "status": "confirmed",
                "source": "rule",
                "confidence": None,
            },
            "user_annotation": "synthetic note",
            "user_explanation": "synthetic user explanation",
            "ai_explanation": "synthetic AI explanation",
        }
        async with engine.connect() as connection:
            original_occurrence = (
                (
                    await connection.execute(
                        select(TransactionOccurrence.__table__).where(
                            TransactionOccurrence.id == occurrence_id
                        )
                    )
                )
                .mappings()
                .one()
            )
            previous_observations = {
                observation["id"]: dict(observation)
                for observation in (
                    await connection.execute(select(TransactionObservation.__table__))
                )
                .mappings()
                .all()
            }
            previous_links = {
                (link.occurrence_id, link.observation_id)
                for link in (
                    await connection.execute(select(occurrence_observation))
                ).all()
            }
        assert len(previous_observations) == len(previous_links) == 1

        async def assert_preserved() -> None:
            nonlocal previous_observations, previous_links
            current = await detail(engine, occurrence_id)
            assert current is not None
            assert current.enrichment.model_dump() == expected_enrichment
            async with engine.connect() as connection:
                occurrence = (
                    (
                        await connection.execute(
                            select(TransactionOccurrence.__table__).where(
                                TransactionOccurrence.id == occurrence_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                observations = {
                    observation["id"]: dict(observation)
                    for observation in (
                        await connection.execute(
                            select(TransactionObservation.__table__)
                        )
                    )
                    .mappings()
                    .all()
                }
                links = {
                    (link.occurrence_id, link.observation_id)
                    for link in (
                        await connection.execute(select(occurrence_observation))
                    ).all()
                }
            for field in (
                "id",
                "account_id",
                "transaction_date",
                "amount_minor",
                "currency",
            ):
                assert occurrence[field] == original_occurrence[field]
            assert all(
                observations.get(key) == value
                for key, value in previous_observations.items()
            )
            assert previous_links <= links
            assert all(
                linked_occurrence == occurrence_id for linked_occurrence, _ in links
            )
            previous_observations, previous_links = observations, links

        for index in range(5):
            (tmp_path / f"overlap-{index}.xlsx").write_bytes(
                workbook([[f"Synthetic preamble {index}"], HEADINGS, pending])
            )
            result = await ingest_xlsx(tmp_path, engine)
            assert result.transactions_added == 0
            await assert_preserved()
        booked = row("01/01/2022", "CONTABILIZZATO", "changed")
        booked[5] = "Bank booked"
        (tmp_path / "booked.xlsx").write_bytes(workbook([HEADINGS, booked]))
        result = await ingest_xlsx(tmp_path, engine)
        assert result.transactions_updated == 1
        await assert_preserved()
        async with engine.connect() as connection:
            files = (await connection.execute(select(SourceFile.__table__))).all()
            observations = (
                await connection.execute(select(TransactionObservation.__table__))
            ).all()
            occurrences = (
                await connection.execute(select(TransactionOccurrence.__table__))
            ).all()
        assert len(files) == len(observations) == 7
        assert [o.booking_status for o in occurrences] == ["booked"]
        enriched = await detail(engine, occurrence_id)
        assert enriched is not None
        assert enriched.enrichment.category.value == "groceries"
        assert enriched.enrichment.user_annotation == "synthetic note"
        assert [observation.details for observation in enriched.observations] == [
            *([None] * 6),
            "changed",
        ]
        assert [observation.category for observation in enriched.observations] == [
            *(["Bank pending"] * 6),
            "Bank booked",
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingestion_and_enrichment_serialize_without_losing_data(
    tmp_path: Path, migrated_url: str
) -> None:
    (tmp_path / "pending.xlsx").write_bytes(
        workbook([HEADINGS, row("01/01/2022", "NON CONTABILIZZATO")])
    )
    engine = create_async_engine(migrated_url)
    try:
        await ingest_xlsx(tmp_path, engine)
        async with engine.connect() as conn:
            occurrence_id = await conn.scalar(select(TransactionOccurrence.id))
        assert occurrence_id is not None
        (tmp_path / "booked.xlsx").write_bytes(
            workbook([HEADINGS, row("01/01/2022", "CONTABILIZZATO")])
        )
        async with engine.begin() as lock:
            await lock.execute(
                text("SELECT id FROM transaction_occurrence WHERE id = :id FOR UPDATE"),
                {"id": occurrence_id},
            )
            ingestion = asyncio.create_task(ingest_xlsx(tmp_path, engine))

            async def ingestion_waiting() -> None:
                while True:
                    async with engine.connect() as conn:
                        count = await conn.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                "AND wait_event_type = 'Lock' AND query LIKE 'UPDATE transaction_occurrence%'"
                            )
                        )
                    if count:
                        return
                    await asyncio.sleep(0.02)

            await asyncio.wait_for(ingestion_waiting(), 5)
            enrichment = asyncio.create_task(
                update_enrichment(
                    engine,
                    occurrence_id,
                    EnrichmentUpdate.model_validate({"user_annotation": "retained"}),
                )
            )
            await asyncio.sleep(0.1)
            assert not enrichment.done()
        await asyncio.gather(ingestion, enrichment)
        result = await detail(engine, occurrence_id)
        assert result is not None
        assert result.booking_status == "booked"
        assert result.enrichment.user_annotation == "retained"
        assert len(result.observations) == 2
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
        async with engine.connect() as connection:
            first_id = await connection.scalar(
                select(TransactionOccurrence.id).order_by(TransactionOccurrence.id)
            )
        assert first_id is not None
        await update_enrichment(
            engine,
            first_id,
            EnrichmentUpdate.model_validate({"user_annotation": "first only"}),
        )
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
        for occurrence in occurrences:
            record = await detail(engine, occurrence.id)
            assert record is not None
            assert record.enrichment.user_annotation == (
                "first only" if occurrence.id == first_id else None
            )
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
