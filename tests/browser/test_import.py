import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

from personal_financial_assistant.ui.app import STATIC


def import_run(state: str) -> dict[str, object]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "state": state,
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": None if state == "running" else "2025-01-01T00:00:01Z",
        "counts": (
            {
                "files_seen": 1,
                "files_processed": 1,
                "files_unchanged": 0,
                "rows_read": 2,
                "transactions_added": 2,
                "transactions_updated": 0,
                "observations_unchanged": 0,
                "unresolved_observations": 1,
            }
            if state in ("succeeded", "no_files")
            else None
        ),
        "error": (
            {"code": "import_failed", "message": "The import could not be completed."}
            if state == "failed"
            else None
        ),
    }


class LocalApp:
    def __init__(self) -> None:
        self.run: dict[str, object] | None = None
        self.starts = 0
        self.pending_start: Route | None = None
        self.stall_start = False
        self.status_failure = False
        self.conflict = False
        self.start_unavailable = False
        self.resolve_unavailable = False
        self.hold_status = False
        self.pending_status: Route | None = None
        self.request_id: str | None = None
        self.runs: dict[str, dict[str, object]] = {}

    def serve(self, route: Route) -> None:
        request = route.request
        path = urlsplit(request.url).path
        if path == "/":
            html = (STATIC / "index.html").read_text(encoding="utf-8")
            route.fulfill(
                content_type="text/html", body=html.replace("__PFA_TOKEN__", "test")
            )
        elif path.startswith("/static/"):
            file = STATIC / Path(path).name
            if file.suffix == ".js":
                content_type = "text/javascript"
            else:
                content_type = "text/css"
            if file.exists():
                route.fulfill(content_type=content_type, path=file)
            else:
                route.fulfill(status=404)
        elif path == "/api/imports/current":
            if self.hold_status:
                self.pending_status = route
            elif self.status_failure:
                route.fulfill(
                    status=503,
                    json={
                        "error": {
                            "code": "coordinator_unavailable",
                            "message": "Unavailable.",
                        }
                    },
                )
            else:
                route.fulfill(json={"run": self.run})
        elif path == "/api/imports/status" and request.method == "POST":
            if self.status_failure:
                route.fulfill(
                    status=503,
                    json={
                        "error": {
                            "code": "coordinator_unavailable",
                            "message": "Unavailable.",
                        }
                    },
                )
            else:
                run_id = json.loads(request.post_data or "{}")["id"]
                tracked = self.runs.get(run_id)
                if self.run and self.run["id"] == run_id:
                    tracked = self.run
                route.fulfill(json={"run": tracked, "current": self.run})
        elif path == "/api/imports/resolve" and request.method == "POST":
            run_id = json.loads(request.post_data or "{}")["id"]
            if self.resolve_unavailable:
                route.fulfill(
                    status=503, json={"error": {"code": "coordinator_unavailable"}}
                )
            elif self.run and self.run["state"] == "running":
                route.fulfill(status=409, json={"error": {"code": "import_conflict"}})
            else:
                if run_id not in self.runs and (
                    not self.run or self.run["id"] != run_id
                ):
                    resolved = import_run("unknown")
                    resolved["id"] = run_id
                    self.runs[run_id] = resolved
                    self.run = resolved
                route.fulfill(json={"id": run_id})
        elif path == "/api/imports" and request.method == "POST":
            self.starts += 1
            body = json.loads(request.post_data or "{}")
            self.request_id = body.get("request_id")
            if not body["input_dir"].strip():
                route.fulfill(
                    status=422,
                    json={
                        "error": {"code": "invalid_input", "message": "Invalid input."}
                    },
                )
                return
            assert body["input_dir"] == "/synthetic"
            if self.stall_start:
                self.pending_start = route
                return
            if self.conflict:
                route.fulfill(
                    status=409,
                    json={
                        "error": {
                            "code": "import_conflict",
                            "message": "An import is running.",
                        }
                    },
                )
                return
            if self.start_unavailable:
                route.fulfill(
                    status=503,
                    json={
                        "error": {
                            "code": "import_not_started",
                            "message": "Storage or import ownership is unavailable.",
                        }
                    },
                )
                return
            self.run = import_run("running")
            self.run["id"] = self.request_id
            route.fulfill(status=202, json={"id": self.run["id"], "state": "running"})
        else:
            route.fulfill(status=404)


@pytest.fixture
def local_app(page: Page) -> LocalApp:
    app = LocalApp()
    page.route("http://127.0.0.1:8765/**", app.serve)
    return app


def test_import_blocks_navigation_and_reattaches(
    page: Page, local_app: LocalApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(
        page.get_by_text("Navigation is unavailable while an import may be running.")
    ).to_be_visible()
    assert local_app.starts == 1

    page.reload()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    assert local_app.run is not None
    own_id = local_app.run["id"]
    local_app.run = import_run("succeeded")
    local_app.run["id"] = own_id
    expect(page.get_by_text("Import completed", exact=False)).to_be_visible(
        timeout=5000
    )
    for label in (
        "Files seen: 1",
        "Files processed: 1",
        "Files unchanged: 0",
        "Rows read: 2",
        "Transactions added: 2",
        "Transactions updated: 0",
        "Observations unchanged: 0",
        "Unresolved observations: 1",
    ):
        expect(page.get_by_text(label, exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            "Unresolved observations could not be confidently linked to a transaction.",
            exact=True,
        )
    ).to_be_visible()
    assert "/synthetic" not in page.url
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_visible()


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ("no_files", "No eligible files"),
        ("failed", "The import could not be completed"),
        ("unknown", "Import outcome is unknown"),
    ],
)
def test_terminal_import_states(
    page: Page, local_app: LocalApp, state: str, message: str
) -> None:
    local_app.run = import_run(state)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    expect(page.get_by_text(message, exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()


def test_timed_out_start_does_not_resubmit_or_unlock(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.clock.install()
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.clock.fast_forward(75001)
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    page.get_by_role("button", name="Chat", exact=True).click()
    expect(page.get_by_text("Navigation is unavailable", exact=False)).to_be_visible()
    page.get_by_role("button", name="Retry status").click()
    assert local_app.starts == 1


def test_unavailable_status_blocks_until_retrieved(
    page: Page, local_app: LocalApp
) -> None:
    local_app.status_failure = True
    page.goto("http://127.0.0.1:8765/")
    expect(page.get_by_role("heading", name="Chat")).to_be_visible()
    page.get_by_role("button", name="Import", exact=True).click()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(
        page.get_by_text("Storage or import ownership may be unavailable", exact=False)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    local_app.status_failure = False
    page.get_by_role("button", name="Retry status").click()
    expect(page.get_by_text("No import has been started.")).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()


def test_invalid_status_does_not_unlock_navigation(
    page: Page, local_app: LocalApp
) -> None:
    local_app.run = import_run("unexpected")
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()


def test_confirmed_conflict_is_reported_and_tracks_the_active_run(
    page: Page, local_app: LocalApp
) -> None:
    local_app.conflict = True
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Your import was not started", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    local_app.run = import_run("running")
    page.get_by_role("button", name="Retry status").click()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    expect(page.get_by_text("Your import was not started", exact=False)).to_be_visible()
    assert local_app.run is not None
    own_id = local_app.run["id"]
    local_app.run = import_run("succeeded")
    local_app.run["id"] = own_id
    expect(page.get_by_text("Import completed", exact=False)).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()
    assert local_app.starts == 1


def test_confirmed_start_unavailability_is_explained_without_unknown_run(
    page: Page, local_app: LocalApp
) -> None:
    local_app.start_unavailable = True
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Your import was not started", exact=False)).to_be_visible()
    expect(
        page.get_by_text("Storage or import ownership is unavailable", exact=False)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()
    assert local_app.starts == 1


def test_other_open_tab_tracks_import_and_blocks_navigation(
    page: Page, local_app: LocalApp
) -> None:
    browser = page.context.browser
    assert browser is not None
    context = browser.new_context()
    other = context.new_page()
    other.route("http://127.0.0.1:8765/**", local_app.serve)
    try:
        for tab in (page, other):
            tab.goto("http://127.0.0.1:8765/")
            tab.wait_for_function("!document.querySelector('#import-start').disabled")
        page.get_by_role("button", name="Import", exact=True).click()
        page.get_by_label("Local folder").fill("/synthetic")
        page.get_by_role("button", name="Start import").click()
        expect(page.get_by_text("Import running", exact=False)).to_be_visible()

        other.get_by_role("button", name="Transactions", exact=True).click()
        expect(other.get_by_text("Import running", exact=False)).to_be_visible()
        expect(other.get_by_role("heading", name="Transactions")).to_be_hidden()
        expect(other.get_by_role("button", name="Start import")).to_be_disabled()
        other.get_by_role("button", name="Chat", exact=True).click()
        expect(
            other.get_by_text(
                "Navigation is unavailable while an import may be running.", exact=True
            )
        ).to_be_visible()

        assert local_app.run is not None
        own_id = local_app.run["id"]
        local_app.run = import_run("succeeded")
        local_app.run["id"] = own_id
        expect(other.get_by_text("Import completed", exact=False)).to_be_visible(
            timeout=5000
        )
        other.get_by_role("button", name="Transactions", exact=True).click()
        expect(other.get_by_role("heading", name="Transactions")).to_be_visible()
        assert local_app.starts == 1
    finally:
        context.close()


def test_other_tab_cannot_navigate_when_current_status_is_unavailable(
    page: Page, local_app: LocalApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    local_app.status_failure = True
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_hidden()
    expect(page.get_by_text("Navigation is unavailable", exact=False)).to_be_visible()
    page.get_by_role("button", name="Import", exact=True).click()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()


def test_idle_tab_detects_running_and_finished_import(
    page: Page, local_app: LocalApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    local_app.run = import_run("running")
    expect(page.get_by_text("Import running", exact=False)).to_be_visible(timeout=5000)
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    local_app.run = import_run("succeeded")
    expect(page.get_by_text("Import completed", exact=False)).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()


def test_navigation_rechecks_after_an_in_flight_stale_status(
    page: Page, local_app: LocalApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    local_app.hold_status = True
    page.wait_for_timeout(1500)
    assert local_app.pending_status is not None
    local_app.run = import_run("running")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_hidden()
    local_app.hold_status = False
    local_app.pending_status.fulfill(json={"run": None})
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Transactions")).to_be_hidden()


def test_competing_run_does_not_resolve_a_pending_start(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.wait_for_timeout(100)
    assert local_app.pending_start is not None
    assert local_app.request_id is not None
    local_app.run = import_run("succeeded")
    page.wait_for_timeout(1500)
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    expect(page.get_by_text("Import completed.", exact=True)).to_be_hidden()
    local_app.pending_start.fulfill(
        status=409,
        json={"error": {"code": "import_conflict", "message": "An import is running."}},
    )
    expect(page.get_by_text("Your import was not started", exact=False)).to_be_visible()


def test_lost_start_response_requires_matching_run_even_after_reload(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.wait_for_timeout(100)
    assert local_app.pending_start is not None
    assert local_app.request_id is not None
    local_app.run = import_run("succeeded")
    local_app.pending_start.abort()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    page.reload()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    own_run = import_run("succeeded")
    own_run["id"] = local_app.request_id
    local_app.run = own_run
    expect(page.get_by_text("Import completed.", exact=True)).to_be_visible(
        timeout=5000
    )
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()


def test_missing_start_can_be_resolved_without_resubmitting(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.wait_for_timeout(100)
    assert local_app.pending_start is not None
    local_app.pending_start.abort()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    page.reload()
    page.get_by_role("button", name="Resolve unrecorded import").click()
    expect(page.get_by_text("Import outcome is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()
    assert local_app.starts == 1
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_visible()


def test_resolution_releases_pending_start_and_ignores_its_late_response(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_role("button", name="Resolve unrecorded import")).to_be_visible()
    assert local_app.pending_start is not None
    delayed = local_app.pending_start
    page.get_by_role("button", name="Resolve unrecorded import").click()
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()
    local_app.stall_start = False
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    delayed.fulfill(
        status=409,
        json={"error": {"code": "import_request_closed", "message": "Recorded."}},
    )
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    assert local_app.starts == 2


def test_failed_resolution_keeps_the_request_locked(
    page: Page, local_app: LocalApp
) -> None:
    pending = "00000000-0000-0000-0000-000000000002"
    local_app.resolve_unavailable = True
    page.add_init_script(f"localStorage.setItem('pfa-pending-import:{pending}', '1')")
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Resolve unrecorded import").click()
    expect(page.get_by_text("could not be resolved", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_hidden()
    assert local_app.starts == 0


def test_matching_run_waits_for_pending_start_response(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.wait_for_timeout(100)
    assert local_app.pending_start is not None
    assert local_app.request_id is not None
    local_app.run = import_run("succeeded")
    local_app.run["id"] = local_app.request_id
    page.wait_for_timeout(1500)
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    local_app.pending_start.fulfill(
        status=202, json={"id": local_app.request_id, "state": "running"}
    )
    expect(page.get_by_text("Import completed.", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_enabled()


def test_matching_running_run_is_shown_while_start_response_is_pending(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.wait_for_timeout(100)
    assert local_app.request_id is not None
    local_app.run = import_run("running")
    local_app.run["id"] = local_app.request_id
    expect(page.get_by_text("Import running", exact=False)).to_be_visible(timeout=5000)
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    page.get_by_role("button", name="Chat", exact=True).click()
    expect(page.get_by_role("heading", name="Chat")).to_be_hidden()


def test_unresolved_request_survives_tab_closure(
    page: Page, local_app: LocalApp
) -> None:
    browser = page.context.browser
    assert browser is not None
    context = browser.new_context()
    context.route("http://127.0.0.1:8765/**", local_app.serve)
    local_app.stall_start = True
    try:
        first = context.new_page()
        first.goto("http://127.0.0.1:8765/")
        first.wait_for_function("!document.querySelector('#import-start').disabled")
        first.get_by_role("button", name="Import", exact=True).click()
        first.get_by_label("Local folder").fill("/synthetic")
        first.get_by_role("button", name="Start import").click()
        first.wait_for_timeout(100)
        assert local_app.pending_start is not None
        assert local_app.request_id is not None
        local_app.run = import_run("succeeded")
        assert local_app.run["id"] != local_app.request_id
        first.close()
        reopened = context.new_page()
        reopened.goto("http://127.0.0.1:8765/")
        expect(
            reopened.get_by_text("Import status is unknown", exact=False)
        ).to_be_visible()
        expect(reopened.get_by_role("button", name="Start import")).to_be_disabled()
        expect(reopened.get_by_text("Import completed.", exact=True)).to_be_hidden()
    finally:
        context.close()


def test_superseded_run_outcome_is_recovered_while_new_run_blocks_navigation(
    page: Page, local_app: LocalApp
) -> None:
    local_app.stall_start = True
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    page.wait_for_timeout(100)
    assert local_app.pending_start is not None
    assert local_app.request_id is not None
    own = import_run("succeeded")
    own["id"] = local_app.request_id
    local_app.runs[local_app.request_id] = own
    local_app.run = import_run("running")
    local_app.pending_start.fulfill(
        status=202, json={"id": local_app.request_id, "state": "running"}
    )
    expect(page.get_by_text("Your import completed", exact=False)).to_be_visible()
    expect(page.get_by_text("Another import is running", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_hidden()
    local_app.run = import_run("succeeded")
    expect(page.get_by_role("button", name="Start import")).to_be_enabled(timeout=5000)
    expect(page.get_by_text("Your import completed", exact=False)).to_be_visible()


def test_multiple_pending_requests_do_not_hide_an_unresolved_one(
    page: Page, local_app: LocalApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    first_id = "00000000-0000-0000-0000-000000000001"
    second_id = "00000000-0000-0000-0000-000000000002"
    page.evaluate(
        """ids => ids.forEach(id => localStorage.setItem('pfa-pending-import:' + id, '1'))""",
        [first_id, second_id],
    )
    local_app.runs[first_id] = import_run("succeeded")
    local_app.run = import_run("running")
    local_app.run["id"] = "00000000-0000-0000-0000-000000000003"
    page.reload()
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_text("Another import is running", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    resolved = import_run("succeeded")
    resolved["id"] = second_id
    local_app.runs[second_id] = resolved
    local_app.run = resolved
    expect(page.get_by_role("button", name="Start import")).to_be_enabled(timeout=5000)


def test_multiple_recovered_outcomes_survive_another_start(
    page: Page, local_app: LocalApp
) -> None:
    browser = page.context.browser
    assert browser is not None
    context = browser.new_context()
    context.route("http://127.0.0.1:8765/**", local_app.serve)
    page = context.new_page()
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    first_id = "00000000-0000-0000-0000-000000000001"
    second_id = "00000000-0000-0000-0000-000000000002"
    page.evaluate(
        """ids => ids.forEach(id => localStorage.setItem('pfa-pending-import:' + id, '1'))""",
        [first_id, second_id],
    )
    local_app.runs[first_id] = import_run("succeeded")
    failed = import_run("failed")
    failed["id"] = second_id
    local_app.runs[second_id] = failed
    local_app.run = failed
    reopened = context.new_page()
    page.close()
    page = reopened
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    outcomes = page.locator("#import-outcomes")
    expect(outcomes.get_by_text(first_id, exact=False)).to_contain_text(
        "Import completed."
    )
    expect(outcomes.get_by_text(second_id, exact=False)).to_contain_text(
        "The import could not be completed."
    )
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    expect(outcomes.get_by_text(second_id, exact=False)).to_be_visible()
    assert (
        page.evaluate(
            "id => localStorage.getItem('pfa-pending-import:' + id)", second_id
        )
        == "1"
    )
    page.get_by_role("button", name="Dismiss recovered outcomes").click()
    expect(outcomes.get_by_text(second_id, exact=False)).to_be_hidden()
    assert (
        page.evaluate(
            "id => localStorage.getItem('pfa-pending-import:' + id)", second_id
        )
        is None
    )
    context.close()


def test_existing_session_pending_id_is_preserved(
    page: Page, local_app: LocalApp
) -> None:
    pending = "00000000-0000-0000-0000-000000000002"
    local_app.run = import_run("succeeded")
    page.add_init_script(f"sessionStorage.setItem('pfa-pending-import', '{pending}')")
    page.goto("http://127.0.0.1:8765/")
    expect(page.get_by_text("Import status is unknown", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    assert (
        page.evaluate("id => localStorage.getItem('pfa-pending-import:' + id)", pending)
        == "1"
    )


def test_unavailable_session_storage_prevents_imports(
    page: Page, local_app: LocalApp
) -> None:
    page.add_init_script(
        "Object.defineProperty(window, 'sessionStorage', "
        "{get() { throw new DOMException('Denied', 'SecurityError'); }});"
    )
    page.goto("http://127.0.0.1:8765/")
    expect(
        page.get_by_text("Browser storage is unavailable", exact=False)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    assert local_app.starts == 0


def test_session_storage_write_failure_prevents_submission(
    page: Page, local_app: LocalApp
) -> None:
    page.add_init_script(
        "Storage.prototype.setItem = () => { throw new DOMException('Denied', 'QuotaExceededError'); };"
    )
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(
        page.get_by_text("Browser storage is unavailable", exact=False)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    assert local_app.starts == 0


def test_folder_rejection_survives_polling_and_does_not_hide_running_status(
    page: Page, local_app: LocalApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("!document.querySelector('#import-start').disabled")
    page.get_by_role("button", name="Import", exact=True).click()
    page.get_by_label("Local folder").fill("   ")
    page.get_by_role("button", name="Start import").click()
    expect(
        page.get_by_text("Enter a non-empty local folder", exact=False)
    ).to_be_visible()
    page.wait_for_timeout(1500)
    expect(
        page.get_by_text("Enter a non-empty local folder", exact=False)
    ).to_be_visible()
    local_app.run = import_run("running")
    expect(page.get_by_text("Import running", exact=False)).to_be_visible(timeout=5000)
    expect(
        page.get_by_text("Enter a non-empty local folder", exact=False)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Start import")).to_be_disabled()
    local_app.run = import_run("succeeded")
    expect(page.get_by_role("button", name="Start import")).to_be_enabled(timeout=5000)
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    expect(
        page.get_by_text("Enter a non-empty local folder", exact=False)
    ).to_be_hidden()
