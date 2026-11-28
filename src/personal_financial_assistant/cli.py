"""CLI parameter validation for local ingestion."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from asyncpg import InterfaceError, PostgresError
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError

from personal_financial_assistant.infrastructure.database import engine_scope
from personal_financial_assistant.infrastructure.settings import (
    SettingsError,
    load_settings,
)
from personal_financial_assistant.ingestion.service import IngestionError, ingest_xlsx
from personal_financial_assistant.ingestion.xlsx_reader import (
    WorkbookError,
    discover_workbooks,
)


class IngestXlsxParameters(BaseModel):
    """Validated inputs for one on-demand import."""

    input_dir: Path

    @field_validator("input_dir", mode="before")
    @classmethod
    def validate_path(cls, value: object) -> object:
        if isinstance(value, (str, Path)) and (
            not str(value).strip() or "\0" in str(value)
        ):
            raise ValueError("Invalid input directory")
        return value


class ParameterError(Exception):
    """A sanitized command-line validation error."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ParameterError("Invalid command or arguments")


def parse_parameters(arguments: Sequence[str]) -> IngestXlsxParameters:
    """Validate an on-demand ingest command without exposing user input."""
    parser = _Parser(prog="personal-financial-assistant", add_help=False)
    parser.add_argument("command", choices=["ingest-xlsx"])
    parser.add_argument("--input-dir", required=True)
    namespace = parser.parse_args(arguments)
    try:
        return IngestXlsxParameters.model_validate({"input_dir": namespace.input_dir})
    except ValidationError:
        raise ParameterError("Invalid input directory") from None


async def serve_ui() -> None:
    """Serve the local browser interface on loopback only."""
    import uvicorn

    from personal_financial_assistant.ui.app import create_app
    from personal_financial_assistant.ui.errors import SanitizedServerErrors

    config = uvicorn.Config(create_app(), host="127.0.0.1", port=8765, access_log=False)
    server_logger = logging.getLogger("uvicorn.error")
    log_filter = SanitizedServerErrors()
    server_logger.addFilter(log_filter)
    try:
        await uvicorn.Server(config).serve()
    finally:
        server_logger.removeFilter(log_filter)


async def run(arguments: Sequence[str]) -> int:
    """Run one command and print only sanitized summaries."""
    if arguments and arguments[0] == "serve-ui":
        if len(arguments) != 1:
            print("Invalid command or arguments", file=sys.stderr)
            return 1
        await serve_ui()
        return 0
    try:
        params = parse_parameters(arguments)
        snapshots = await discover_workbooks(params.input_dir)
        if not snapshots:
            print(
                "No eligible XLSX files. Files seen: 0; processed: 0; unchanged: 0; "
                "rows read: 0; transactions added: 0; transactions updated: 0; "
                "observations unchanged: 0; unresolved observations: 0."
            )
            return 0
        settings = await load_settings()
        async with engine_scope(settings) as engine:
            result = await ingest_xlsx(params.input_dir, engine, snapshots=snapshots)
        print(
            f"Files seen: {result.files_seen}; processed: {result.files_processed}; "
            f"unchanged: {result.files_unchanged}; rows read: {result.rows_read}; "
            f"transactions added: {result.transactions_added}; "
            f"transactions updated: {result.transactions_updated}; "
            f"observations unchanged: {result.observations_unchanged}; "
            f"unresolved observations: {result.unresolved_observations}."
        )
        evaluation = result.evaluation
        if evaluation.failed or evaluation.pending or evaluation.unknown:
            print(
                "Import completed; rule evaluation incomplete: "
                f"failed: {evaluation.failed}; pending: {evaluation.pending}; "
                f"unknown: {evaluation.unknown}. Inspect work before retrying.",
                file=sys.stderr,
            )
        return 0
    except (ParameterError, SettingsError, WorkbookError, IngestionError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError, PostgresError, InterfaceError, OSError, TimeoutError:
        print("Import failed: database or storage unavailable.", file=sys.stderr)
        return 1


def main() -> None:
    """Run the local command."""
    raise SystemExit(asyncio.run(run(sys.argv[1:])))
