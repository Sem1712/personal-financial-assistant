import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio

from personal_financial_assistant.infrastructure.models import UIImportRun
from personal_financial_assistant.ui.app import create_app
from personal_financial_assistant.ui.import_coordinator import (
    CoordinatorUnavailable,
    ImportConflict,
    ImportNotStarted,
    ImportRequestClosed,
)

ORIGIN = "http://127.0.0.1:8765"
RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


class Coordinator:
    def __init__(self) -> None:
        self.started: list[Path] = []
        self.request_id: UUID | None = None
        self.error: Exception | None = None
        self.run: UIImportRun | None = None
        self.tracked: UIImportRun | None = None

    async def start(self, directory: Path, *, run_id: UUID | None = None) -> UUID:
        if self.error is not None:
            raise self.error
        self.started.append(directory)
        self.request_id = run_id
        return run_id or RUN_ID

    async def current(self) -> UIImportRun | None:
        if self.error is not None:
            raise self.error
        return self.run

    async def status(
        self, run_id: UUID
    ) -> tuple[UIImportRun | None, UIImportRun | None]:
        if self.error is not None:
            raise self.error
        assert run_id == RUN_ID
        return self.tracked, self.run

    async def resolve(self, run_id: UUID) -> UUID:
        if self.error is not None:
            raise self.error
        return run_id


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[tuple[httpx.AsyncClient, Coordinator]]:
    app = create_app()
    coordinator = Coordinator()
    app.state.coordinator = coordinator
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN
    ) as test_client:
        bootstrap = await test_client.get("/")
        match = re.search(r'<meta name="pfa-token" content="([^"]+)">', bootstrap.text)
        assert match is not None
        test_client.headers.update({"x-pfa-token": match.group(1), "origin": ORIGIN})
        yield test_client, coordinator


@pytest.mark.asyncio
async def test_start_and_current_contract(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    response = await http.post("/api/imports", json={"input_dir": "private-folder"})
    assert response.status_code == 202
    assert response.json() == {"id": str(RUN_ID), "state": "running"}
    assert "private-folder" not in response.text
    assert coordinator.started == [Path("private-folder").absolute()]
    current = await http.get("/api/imports/current")
    assert current.status_code == 200
    assert current.json() == {"run": None}


@pytest.mark.asyncio
async def test_client_request_id_is_used_as_run_id(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    response = await http.post(
        "/api/imports", json={"input_dir": "private-folder", "request_id": str(RUN_ID)}
    )
    assert response.status_code == 202
    assert response.json()["id"] == str(RUN_ID)
    assert coordinator.request_id == RUN_ID


@pytest.mark.asyncio
async def test_invalid_request_id_is_rejected(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    response = await http.post(
        "/api/imports", json={"input_dir": "private-folder", "request_id": "not-a-uuid"}
    )
    assert response.status_code == 422
    assert not coordinator.started


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["", "  ", "bad\0path"])
async def test_invalid_folders_are_rejected_without_disclosure(
    client: tuple[httpx.AsyncClient, Coordinator], path: str
) -> None:
    http, coordinator = client
    response = await http.post("/api/imports", json={"input_dir": path})
    assert response.status_code == 422
    if path:
        assert path not in response.text
    assert not coordinator.started


@pytest.mark.asyncio
async def test_current_reports_all_counts(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    now = datetime.now(UTC)
    coordinator.run = UIImportRun(
        id=RUN_ID,
        state="succeeded",
        started_at=now,
        finished_at=now,
        files_seen=1,
        files_processed=1,
        files_unchanged=0,
        rows_read=2,
        transactions_added=2,
        transactions_updated=0,
        observations_unchanged=0,
        unresolved_observations=1,
    )
    response = await http.get("/api/imports/current")
    assert response.status_code == 200
    run = response.json()["run"]
    assert run["id"] == str(RUN_ID)
    assert run["state"] == "succeeded"
    assert run["error"] is None
    assert run["counts"] == {
        "files_seen": 1,
        "files_processed": 1,
        "files_unchanged": 0,
        "rows_read": 2,
        "transactions_added": 2,
        "transactions_updated": 0,
        "observations_unchanged": 0,
        "unresolved_observations": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ImportConflict(), 409, "import_conflict"),
        (CoordinatorUnavailable(), 503, "coordinator_unavailable"),
        (ImportNotStarted(), 503, "import_not_started"),
        (ImportRequestClosed(), 409, "import_request_closed"),
    ],
)
async def test_import_errors_are_explicit_and_sanitized(
    client: tuple[httpx.AsyncClient, Coordinator],
    error: Exception,
    status: int,
    code: str,
) -> None:
    http, coordinator = client
    coordinator.error = error
    response = await http.post("/api/imports", json={"input_dir": "private-folder"})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "private-folder" not in response.text


@pytest.mark.asyncio
async def test_unavailable_current_status_is_not_an_empty_success(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    coordinator.error = CoordinatorUnavailable()
    response = await http.get("/api/imports/current")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "coordinator_unavailable"


@pytest.mark.asyncio
async def test_status_returns_tracked_and_current_runs(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    now = datetime.now(UTC)
    coordinator.tracked = UIImportRun(
        id=RUN_ID, state="unknown", started_at=now, finished_at=now
    )
    coordinator.run = UIImportRun(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        state="running",
        started_at=now,
    )
    response = await http.post("/api/imports/status", json={"id": str(RUN_ID)})
    assert response.status_code == 200
    assert response.json()["run"]["id"] == str(RUN_ID)
    assert response.json()["run"]["state"] == "unknown"
    assert response.json()["current"]["state"] == "running"


@pytest.mark.asyncio
async def test_status_rejects_bad_ids_and_reports_unavailable(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    assert (
        await http.post("/api/imports/status", json={"id": "invalid"})
    ).status_code == 422
    coordinator.error = CoordinatorUnavailable()
    response = await http.post("/api/imports/status", json={"id": str(RUN_ID)})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "coordinator_unavailable"


@pytest.mark.asyncio
async def test_resolve_contract_validates_and_reports_errors(
    client: tuple[httpx.AsyncClient, Coordinator],
) -> None:
    http, coordinator = client
    response = await http.post("/api/imports/resolve", json={"id": str(RUN_ID)})
    assert response.status_code == 200
    assert response.json() == {"id": str(RUN_ID)}
    assert (
        await http.post("/api/imports/resolve", json={"id": "invalid"})
    ).status_code == 422
    coordinator.error = CoordinatorUnavailable()
    assert (
        await http.post("/api/imports/resolve", json={"id": str(RUN_ID)})
    ).status_code == 503
