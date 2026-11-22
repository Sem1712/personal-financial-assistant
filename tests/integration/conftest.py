from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

from alembic import command


@pytest.fixture
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
def migrated_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("PFA_DATABASE_URL", postgres_url)
    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    command.upgrade(Config(str(config_path)), "head")
    return postgres_url
