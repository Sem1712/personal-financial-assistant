import asyncio
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from personal_financial_assistant.ingestion.worker_client import WorkbookWorker
from personal_financial_assistant.ingestion.xlsx_reader import FileSnapshot
from personal_financial_assistant.ui.app import create_app
from tests.fixtures.ui import create_export


def test_real_browser_import_and_transaction_refresh(
    migrated_url: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del migrated_url
    exports = tmp_path / "exports"
    exports.mkdir()
    create_export(exports)
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
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                page = context.new_page()
                other = context.new_page()
                urls: list[str] = []
                page.on("request", lambda request: urls.append(request.url))
                page.goto("http://127.0.0.1:8765/")
                other.goto("http://127.0.0.1:8765/")
                expect(other.locator("#navigation-status")).to_have_text("")
                expect(page.get_by_role("heading", name="Chat")).to_be_visible()
                expect(page.locator("#navigation-status")).to_have_text("")
                page.get_by_role("button", name="Go to transactions").click()
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
                page.get_by_role("button", name="View details").click()
                expect(
                    page.get_by_text("Operation: Synthetic purchase", exact=True)
                ).to_be_visible()
                expect(page.get_by_text("Bank suggestion: Food")).to_be_visible()
                page.get_by_label("Description").fill("absent")
                page.get_by_role("button", name="Apply filters").click()
                expect(
                    page.get_by_text("No transactions match", exact=False)
                ).to_be_visible()
                page.get_by_role("button", name="Clear filters").click()
                expect(page.get_by_text("-12.34 EUR", exact=True)).to_be_visible()
                page.get_by_role("button", name="Import", exact=True).click()
                page.get_by_label("Local folder").fill(str(exports))
                page.get_by_role("button", name="Start import").click()
                expect(
                    page.get_by_text("Files unchanged: 1", exact=True)
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
                assert all(url.startswith("http://127.0.0.1:8765/") for url in urls)
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
