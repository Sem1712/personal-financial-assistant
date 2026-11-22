import asyncio

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command


async def execute(url: str, statement: str) -> object:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text(statement))
            return result.scalar() if result.returns_rows else None
    finally:
        await engine.dispose()


@pytest.mark.parametrize("existing", [False, True])
def test_upgrade_preserves_existing_schema(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    monkeypatch.setenv("PFA_DATABASE_URL", postgres_url)
    if existing:
        asyncio.run(execute(postgres_url, "CREATE TABLE existing_data (value integer)"))
        asyncio.run(execute(postgres_url, "INSERT INTO existing_data VALUES (42)"))
    command.upgrade(Config("alembic.ini"), "head")
    assert (
        asyncio.run(execute(postgres_url, "SELECT version_num FROM alembic_version"))
        == "0003_empty_source"
    )
    if existing:
        assert (
            asyncio.run(execute(postgres_url, "SELECT value FROM existing_data")) == 42
        )


def test_upgrade_preserves_supported_schema_data(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PFA_DATABASE_URL", postgres_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0001_ingestion_schema")
    statements = [
        (
            "INSERT INTO selected_account (id, account_reference, display_label) "
            "VALUES (1, 'synthetic', 'label')"
        ),
        (
            "INSERT INTO source_file (sha256, transaction_row_count, account_id) "
            "VALUES (repeat('a', 64), 2, 1)"
        ),
        (
            "INSERT INTO transaction_observation "
            "(id, source_file_sha256, sheet_index, row_number, account_id, transaction_date, "
            "amount_minor, currency, operation, details, booking_status, category, candidate_key, occurrence_ordinal) "
            "VALUES (1, repeat('a', 64), 0, 2, 1, '2022-01-01', -500, 'EUR', 'op', 'detail', 'booked', 'cat', repeat('b', 64), 1), "
            "(2, repeat('a', 64), 0, 3, 1, '2022-01-01', -500, 'EUR', 'op2', 'detail2', 'booked', 'cat2', repeat('b', 64), 2)"
        ),
        (
            "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) "
            "VALUES (1, 1, '2022-01-01', -500, 'EUR', 'booked', 'confirmed'), "
            "(2, 1, '2022-01-01', -500, 'EUR', 'pending', 'unresolved')"
        ),
        "INSERT INTO occurrence_observation VALUES (1, 1), (2, 2)",
    ]
    for statement in statements:
        asyncio.run(execute(postgres_url, statement))
    command.upgrade(config, "head")
    checks = [
        "SELECT count(*) = 1 FROM selected_account WHERE id = 1 AND account_reference = 'synthetic' AND display_label = 'label'",
        "SELECT count(*) = 1 FROM source_file WHERE sha256 = repeat('a', 64) AND transaction_row_count = 2 AND account_id = 1",
        "SELECT count(*) = 2 FROM transaction_observation WHERE account_id = 1 AND amount_minor = -500 AND currency = 'EUR' AND booking_status = 'booked' AND candidate_key = repeat('b', 64)",
        "SELECT count(*) = 1 FROM transaction_observation WHERE id = 2 AND row_number = 3 AND details = 'detail2' AND category = 'cat2' AND occurrence_ordinal = 2",
        "SELECT count(*) = 1 FROM transaction_occurrence WHERE id = 1 AND booking_status = 'booked' AND reconciliation_state = 'confirmed'",
        "SELECT count(*) = 1 FROM transaction_occurrence WHERE id = 2 AND booking_status IS NULL AND reconciliation_state = 'unresolved'",
        "SELECT count(*) = 1 FROM occurrence_observation WHERE occurrence_id = 1 AND observation_id = 1",
        "SELECT count(*) = 1 FROM occurrence_observation",
    ]
    for statement in checks:
        assert asyncio.run(execute(postgres_url, statement)) is True
    with pytest.raises(RuntimeError, match="unknown booking status"):
        command.downgrade(config, "0001_ingestion_schema")


def test_empty_source_constraint_and_downgrade(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PFA_DATABASE_URL", postgres_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    asyncio.run(
        execute(
            postgres_url,
            "INSERT INTO source_file (sha256, transaction_row_count) VALUES (repeat('a', 64), 0)",
        )
    )
    with pytest.raises(IntegrityError):
        asyncio.run(
            execute(
                postgres_url,
                "INSERT INTO source_file (sha256, transaction_row_count) VALUES (repeat('b', 64), 1)",
            )
        )
    with pytest.raises(RuntimeError, match="empty sources have no account"):
        command.downgrade(config, "0002_unknown_status")
