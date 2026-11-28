"""HTTP contracts for locally initiated imports."""

import asyncio
from pathlib import Path
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from personal_financial_assistant.infrastructure.models import UIImportRun
from personal_financial_assistant.rules import EvaluationSummary

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
    coordinator = coordinator_for(request)
    run = await coordinator.current()
    return {"run": await _serialize_with_evaluation(coordinator, run)}


@router.post("/status")
async def import_status(
    body: ImportStatusRequest, request: Request
) -> dict[str, object]:
    coordinator = coordinator_for(request)
    run, current = await coordinator.status(body.id)
    rendered = await _serialize_with_evaluation(coordinator, run)
    if run is not None and current is not None and run.id == current.id:
        rendered_current = rendered
    else:
        rendered_current = await _serialize_with_evaluation(coordinator, current)
    return {"run": rendered, "current": rendered_current}


@router.post("/resolve")
async def resolve_import(body: ImportStatusRequest, request: Request) -> dict[str, str]:
    run_id = await coordinator_for(request).resolve(body.id)
    return {"id": str(run_id)}


async def _serialize_with_evaluation(
    coordinator: ImportCoordinator, run: UIImportRun | None
) -> dict[str, object] | None:
    summary = (
        await coordinator.evaluation_summary(run.id)
        if run is not None and run.state == "succeeded"
        else None
    )
    return _serialize_run(run, summary)


def _serialize_run(
    run: UIImportRun | None, evaluation: EvaluationSummary | None
) -> dict[str, object] | None:
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
    serialized: dict[str, object] = {
        "id": str(run.id),
        "state": run.state,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "counts": counts,
        "error": error,
    }
    if evaluation is not None:
        serialized["evaluation"] = {
            "attempted": evaluation.attempted,
            "completed": evaluation.completed,
            "failed": evaluation.failed,
            "pending": evaluation.pending,
            "unknown": evaluation.unknown,
        }
    return serialized
