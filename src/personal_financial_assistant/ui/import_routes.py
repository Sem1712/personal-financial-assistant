"""HTTP contracts for locally initiated imports."""

import asyncio
from pathlib import Path
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from personal_financial_assistant.infrastructure.models import UIImportRun

from .import_coordinator import (
    CoordinatorUnavailable,
    ImportCoordinator,
    ImportNotStarted,
)

router = APIRouter(prefix="/api/imports")


class ImportRequest(BaseModel):
    input_dir: str
    request_id: UUID | None = None

    @field_validator("input_dir")
    @classmethod
    def validate_directory(cls, value: str) -> str:
        if not value.strip() or "\0" in value:
            raise ValueError("Invalid input directory")
        return value


class ImportStatusRequest(BaseModel):
    id: UUID


def coordinator_for(request: Request) -> ImportCoordinator:
    coordinator = cast(ImportCoordinator | None, request.app.state.coordinator)
    if coordinator is None:
        raise CoordinatorUnavailable
    return coordinator


@router.post("", status_code=202)
async def start_import(body: ImportRequest, request: Request) -> dict[str, str]:
    try:
        directory = await asyncio.to_thread(Path(body.input_dir).absolute)
    except OSError:
        raise ImportNotStarted from None
    try:
        coordinator = coordinator_for(request)
    except CoordinatorUnavailable:
        raise ImportNotStarted from None
    run_id = await coordinator.start(directory, run_id=body.request_id)
    return {"id": str(run_id), "state": "running"}


@router.get("/current")
async def current_import(request: Request) -> dict[str, object]:
    run = await coordinator_for(request).current()
    return {"run": _serialize_run(run)}


@router.post("/status")
async def import_status(
    body: ImportStatusRequest, request: Request
) -> dict[str, object]:
    run, current = await coordinator_for(request).status(body.id)
    return {"run": _serialize_run(run), "current": _serialize_run(current)}


@router.post("/resolve")
async def resolve_import(body: ImportStatusRequest, request: Request) -> dict[str, str]:
    run_id = await coordinator_for(request).resolve(body.id)
    return {"id": str(run_id)}


def _serialize_run(run: UIImportRun | None) -> dict[str, object] | None:
    if run is None:
        return None
    counts = None
    if run.state in ("succeeded", "no_files"):
        counts = {
            "files_seen": run.files_seen,
            "files_processed": run.files_processed,
            "files_unchanged": run.files_unchanged,
            "rows_read": run.rows_read,
            "transactions_added": run.transactions_added,
            "transactions_updated": run.transactions_updated,
            "observations_unchanged": run.observations_unchanged,
            "unresolved_observations": run.unresolved_observations,
        }
    error = (
        {"code": run.error_code, "message": run.error_message}
        if run.state == "failed"
        else None
    )
    return {
        "id": str(run.id),
        "state": run.state,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "counts": counts,
        "error": error,
    }
