"""Disposable synthetic database and real local UI for the enrichment exercise."""

import asyncio
import os
import signal
import socket
from pathlib import Path

import uvicorn
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    update_enrichment,
)
from personal_financial_assistant.ui.app import create_app


async def seed(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, booking_status, reconciliation_state) "
                    "VALUES (1, 1, '2025-01-02', -1500, 'EUR', 'booked', 'confirmed'), (2, 1, '2025-01-01', -2000, 'EUR', 'booked', 'confirmed')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO source_file (sha256, transaction_row_count, account_id) VALUES (repeat('a',64), 2, 1)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO transaction_observation (id, source_file_sha256, sheet_index, row_number, account_id, transaction_date, amount_minor, currency, operation, details, booking_status, category, candidate_key, occurrence_ordinal) "
                    "VALUES (1, repeat('a',64), 0, 1, 1, '2025-01-02', -1500, 'EUR', 'Synthetic classified purchase', 'Recorded evidence', 'booked', 'Bank suggestion', repeat('b',64), 1), "
                    "(2, repeat('a',64), 0, 2, 1, '2025-01-01', -2000, 'EUR', 'Synthetic unclassified purchase', NULL, 'booked', NULL, repeat('c',64), 1)"
                )
            )
            await conn.execute(
                text("INSERT INTO occurrence_observation VALUES (1, 1), (2, 2)")
            )
        await update_enrichment(
            engine,
            1,
            EnrichmentUpdate.model_validate(
                {
                    "transaction_type": {
                        "value": "expense",
                        "status": "confirmed",
                        "source": "user",
                    },
                    "category": {
                        "value": "groceries",
                        "status": "provisional",
                        "source": "ai",
                        "confidence": "72.5",
                    },
                    "budget_treatment": {
                        "value": "excluded",
                        "status": "confirmed",
                        "source": "rule",
                    },
                    "user_annotation": "Synthetic note",
                    "user_explanation": "Synthetic user explanation",
                    "ai_explanation": "Synthetic AI interpretation",
                }
            ),
        )
    finally:
        await engine.dispose()


def main() -> None:
    previous_url = os.environ.get("PFA_DATABASE_URL")
    try:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 8765))
            listener.listen(128)
            with PostgresContainer("postgres:17", driver="asyncpg") as postgres:
                url = postgres.get_connection_url()
                os.environ["PFA_DATABASE_URL"] = url
                command.upgrade(
                    Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")),
                    "head",
                )
                asyncio.run(seed(url))
                print("Synthetic enrichment demo: http://127.0.0.1:8765/", flush=True)
                server = uvicorn.Server(
                    uvicorn.Config(create_app(), log_level="warning", access_log=False)
                )
                server.run(sockets=[listener])
    finally:
        if previous_url is None:
            os.environ.pop("PFA_DATABASE_URL", None)
        else:
            os.environ["PFA_DATABASE_URL"] = previous_url


def interrupt(_signal: int, _frame: object) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt)
    try:
        main()
    except KeyboardInterrupt:
        pass
