import asyncio
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import (
    ConsoleMessage,
    Request,
    Response,
    Route,
    expect,
    sync_playwright,
)

from personal_financial_assistant.ingestion.worker_client import WorkbookWorker
from personal_financial_assistant.ingestion.xlsx_reader import FileSnapshot
from personal_financial_assistant.ui.app import create_app
from tests.fixtures.intesa_xlsx import HEADINGS, workbook
from tests.fixtures.ui import create_export


def test_real_browser_import_and_transaction_refresh(
    migrated_url: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    pytestconfig: pytest.Config,
) -> None:
    del migrated_url
    exports = tmp_path / "exports"
    exports.mkdir()
    create_export(exports)
    (exports / "synthetic-pages.xlsx").write_bytes(
        workbook(
            [
                HEADINGS,
                *[
                    [
                        "31/12/2024",
                        f"Synthetic older record {index}",
                        "Pagination evidence",
                        "TEST-ACCOUNT",
                        "CONTABILIZZATO",
                        "Food",
                        "EUR",
                        -index,
                    ]
                    for index in range(1, 101)
                ],
            ]
        )
    )
    entered = threading.Event()
    release = threading.Event()
    discover = WorkbookWorker.discover

    async def delayed_discovery(
        worker: WorkbookWorker, directory: Path
    ) -> list[FileSnapshot]:
        entered.set()
        if not await asyncio.to_thread(release.wait, 10):
            raise TimeoutError("Test did not release workbook discovery.")
        return await discover(worker, directory)

    monkeypatch.setattr(WorkbookWorker, "discover", delayed_discovery)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", 8765))
    except OSError:
        listener.close()
        pytest.skip("Local UI port 8765 is already in use.")
    listener.listen(128)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host="127.0.0.1",
            port=8765,
            access_log=False,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            threading.Event().wait(0.05)
        assert server.started, "Local UI failed to start."
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel=pytestconfig.getoption("--browser-channel")
            )
            try:
                context = browser.new_context()
                base_url = "http://127.0.0.1:8765/"
                urls: list[str] = []
                console_errors: list[tuple[str, str]] = []
                script_errors: list[str] = []
                asset_responses: dict[str, list[Response]] = {}
                http_failures: list[tuple[str, int]] = []
                request_failures: list[tuple[str, str | None]] = []
                active_requests: set[Request] = set()
                reload_requests: set[Request] = set()
                expected_abort_urls: set[str] = set()

                def loopback_only(route: Route) -> None:
                    if route.request.url.startswith(base_url):
                        route.continue_()
                    else:
                        route.abort()

                def record_asset(response: Response) -> None:
                    if response.url.startswith(f"{base_url}static/"):
                        asset_responses.setdefault(response.url, []).append(response)
                    if response.status >= 400:
                        http_failures.append((response.url, response.status))

                def record_request(request: Request) -> None:
                    urls.append(request.url)
                    active_requests.add(request)

                def record_failure(request: Request) -> None:
                    active_requests.discard(request)
                    if (
                        request in reload_requests
                        and request.failure == "net::ERR_ABORTED"
                    ):
                        expected_abort_urls.add(request.url)
                    else:
                        request_failures.append((request.url, request.failure))

                def record_console(message: ConsoleMessage) -> None:
                    if message.type == "error":
                        console_errors.append((message.text, message.location["url"]))

                context.on("request", record_request)
                context.on(
                    "requestfinished", lambda request: active_requests.discard(request)
                )
                context.on("requestfailed", record_failure)
                context.on("response", record_asset)
                context.route("**/*", loopback_only)
                page = context.new_page()
                other = context.new_page()
                for tab in (page, other):
                    tab.on("console", record_console)
                    tab.on("pageerror", lambda error: script_errors.append(str(error)))
                response = page.goto(base_url)
                assert response is not None
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["content-security-policy"] == (
                    "default-src 'self'; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'"
                )
                assert f"{base_url}static/bootstrap.min.css" in urls
                assert page.locator("head link[rel=stylesheet]").evaluate_all(
                    "links => links.map(link => new URL(link.href).pathname)"
                ) == ["/static/bootstrap.min.css", "/static/styles.css"]
                assert (
                    page.locator("#category").evaluate(
                        "element => getComputedStyle(element).backgroundImage"
                    )
                    == "none"
                )
                page.keyboard.press("Tab")
                expect(
                    page.get_by_role("link", name="Skip to main content")
                ).to_be_focused()
                page.keyboard.press("Enter")
                expect(page.locator("#main-content")).to_be_focused()
                other.goto(base_url)
                expect(other.locator("#navigation-status")).to_have_text("")
                expect(page.get_by_role("heading", name="Chat")).to_be_visible()
                expect(page.locator("#navigation-status")).to_have_text("")
                page.get_by_role("button", name="Go to transactions").click()
                expect(page.locator("#transactions-heading")).to_be_focused()
                expect(
                    page.get_by_role("button", name="Transactions", exact=True)
                ).to_have_attribute("aria-current", "page")
                expect(
                    page.get_by_text("No recorded transactions", exact=False)
                ).to_be_visible()
                page.get_by_role("button", name="Import transactions").click()
                page.get_by_label("Local folder").fill(str(exports))
                page.get_by_role("button", name="Start import").click()
                assert entered.wait(10)
                expect(page.get_by_text("Import running", exact=False)).to_be_visible()
                expect(other.get_by_text("Import running", exact=False)).to_be_visible(
                    timeout=5000
                )
                other.get_by_role("button", name="Transactions", exact=True).click()
                expect(other.get_by_role("heading", name="Transactions")).to_be_hidden()
                page.get_by_role("button", name="Transactions", exact=True).click()
                expect(
                    page.get_by_text(
                        "Navigation is unavailable while an import may be running.",
                        exact=True,
                    )
                ).to_be_visible()
                reload_requests.update(
                    request
                    for request in active_requests
                    if request.frame.page == page
                    and request.url
                    in {
                        f"{base_url}api/imports/current",
                        f"{base_url}api/imports/status",
                    }
                )
                page.reload()
                expect(page.get_by_text("Import running", exact=False)).to_be_visible()
                release.set()
                expect(page.get_by_text("Import completed", exact=False)).to_be_visible(
                    timeout=30000
                )
                expect(
                    other.get_by_text("Import completed", exact=False)
                ).to_be_visible(timeout=30000)
                other.get_by_role("button", name="Transactions", exact=True).click()
                expect(other.get_by_text("-12.34 EUR", exact=True)).to_be_visible()
                page.get_by_role("button", name="Transactions", exact=True).click()
                expect(page.get_by_text("-12.34 EUR", exact=True)).to_be_visible()
                detail_button = (
                    page.locator(".transaction-row")
                    .filter(has=page.get_by_text("-12.34 EUR", exact=True))
                    .get_by_role("button", name="Details", exact=True)
                )
                detail_button.click()
                expect(detail_button).to_be_focused()
                expect(
                    page.get_by_text("Operation: Synthetic purchase", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Bank suggestion: Food")).to_be_visible()
                detail_button.click()
                expect(detail_button).to_be_focused()
                expect(page.locator(".transaction-row")).to_have_count(100)
                page.get_by_role("button", name="Next page").first.click()
                expect(page.locator("#transaction-status")).to_have_text(
                    "1 transactions on this page."
                )
                expect(page.locator("#filters-summary")).to_have_text(
                    "All recorded transactions"
                )
                page.get_by_role("button", name="Previous page").first.click()
                expect(page.get_by_text("-12.34 EUR", exact=True)).to_be_visible()
                for width in (320, 768, 1440):
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                page.get_by_text("Filter your records", exact=True).click()
                page.get_by_label("Description").fill("absent")
                page.get_by_role("button", name="Apply filters").click()
                expect(
                    page.get_by_text("No transactions match", exact=False)
                ).to_be_visible()
                expect(page.locator("#filters-summary")).to_have_text(
                    "Applied filters: Description: absent"
                )
                page.get_by_role("button", name="Clear filters").click()
                expect(page.get_by_text("-12.34 EUR", exact=True)).to_be_visible()
                page.get_by_role("button", name="Import", exact=True).click()
                page.get_by_label("Local folder").fill(str(exports))
                page.get_by_role("button", name="Start import").click()
                expect(
                    page.get_by_text("Files unchanged: 2", exact=True)
                ).to_be_visible(timeout=30000)
                empty = tmp_path / "empty"
                empty.mkdir()
                page.get_by_label("Local folder").fill(str(empty))
                page.get_by_role("button", name="Start import").click()
                expect(
                    page.get_by_text("No eligible files", exact=False)
                ).to_be_visible(timeout=30000)
                (empty / "invalid.xlsx").write_bytes(b"invalid")
                page.get_by_role("button", name="Start import").click()
                expect(
                    page.get_by_text(
                        "An export is invalid, unreadable, or changed", exact=False
                    )
                ).to_be_visible(timeout=30000)
                assert all(url.startswith(base_url) for url in urls)
                for asset in (
                    "bootstrap.min.css",
                    "styles.css",
                    "app.js",
                    "import.js",
                    "chat.js",
                    "transactions.js",
                ):
                    deliveries = asset_responses[f"{base_url}static/{asset}"]
                    assert deliveries
                    for delivered in deliveries:
                        assert delivered.status == 200
                        assert delivered.headers["cache-control"] == "no-store"
                        assert (
                            delivered.headers["content-security-policy"]
                            == response.headers["content-security-policy"]
                        )
                assert not script_errors
                assert not request_failures
                favicon = f"{base_url}favicon.ico"
                assert all(
                    url == favicon and status == 404 for url, status in http_failures
                ), http_failures
                unexpected_console = [
                    text
                    for text, url in console_errors
                    if not (
                        (url == favicon and "status of 404" in text)
                        or (url in expected_abort_urls and "ERR_ABORTED" in text)
                    )
                ]
                assert not unexpected_console, unexpected_console
                assert all(
                    str(tmp_path) not in url and "absent" not in url for url in urls
                )
                assert str(tmp_path) not in caplog.text
                assert "Synthetic purchase" not in caplog.text
                assert "-12.34" not in caplog.text
            finally:
                browser.close()
    finally:
        release.set()
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive(), "Local UI did not shut down."
