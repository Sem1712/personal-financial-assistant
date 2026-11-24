import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

from personal_financial_assistant.ui.app import STATIC
from tests.browser.test_import import import_run


class TransactionApp:
    def __init__(self) -> None:
        self.searches: list[dict[str, object]] = []
        self.empty_history = False
        self.fail_search = False
        self.stall_search = False
        self.run: dict[str, object] | None = None

    def serve(self, route: Route) -> None:
        request = route.request
        path = urlsplit(request.url).path
        if path == "/":
            route.fulfill(
                content_type="text/html",
                body=(STATIC / "index.html")
                .read_text(encoding="utf-8")
                .replace("__PFA_TOKEN__", "test"),
            )
        elif path.startswith("/static/"):
            file = STATIC / Path(path).name
            route.fulfill(
                content_type="text/javascript" if file.suffix == ".js" else "text/css",
                path=file,
            )
        elif path == "/api/imports/current":
            route.fulfill(json={"run": self.run})
        elif path == "/api/imports/status":
            run_id = json.loads(request.post_data or "{}")["id"]
            tracked = self.run if self.run and self.run["id"] == run_id else None
            route.fulfill(json={"run": tracked, "current": self.run})
        elif path == "/api/imports" and request.method == "POST":
            self.run = import_run("running")
            self.run["id"] = json.loads(request.post_data or "{}")["request_id"]
            route.fulfill(status=202, json={"id": self.run["id"], "state": "running"})
        elif path == "/api/transactions/categories":
            route.fulfill(json={"categories": ["Food", "<b>Travel</b>"]})
        elif path == "/api/transactions/search":
            self.searches.append(json.loads(request.post_data or "{}"))
            if self.stall_search:
                return
            if self.fail_search:
                route.fulfill(status=503, json={"error": {"message": "Unavailable."}})
                return
            body = self.searches[-1]
            items = (
                []
                if self.empty_history or body.get("text") == "absent"
                else [
                    {
                        "id": "9223372036854775807" if not body.get("cursor") else "2",
                        "date": "2025-01-15",
                        "amount_minor": "-9223372036854775808",
                        "currency": "EUR",
                        "booking_status": "unknown",
                        "reconciliation_state": "unresolved",
                        "ongoing_expense": False,
                    }
                ]
            )
            route.fulfill(
                json={
                    "items": items,
                    "next_cursor": "next" if items and not body.get("cursor") else None,
                    "history_exists": not self.empty_history,
                }
            )
        elif path == "/api/transactions/detail":
            route.fulfill(
                json={
                    "id": "9223372036854775807",
                    "date": "2025-01-15",
                    "amount_minor": "-9223372036854775808",
                    "currency": "EUR",
                    "booking_status": "unknown",
                    "reconciliation_state": "unresolved",
                    "ongoing_expense": False,
                    "observations": [
                        {
                            "operation": "<img src=x onerror=alert(1)>",
                            "details": None,
                            "category": "Food",
                            "booking_status": "booked",
                        },
                        {
                            "operation": "Other",
                            "details": "Evidence",
                            "category": "<b>Travel</b>",
                            "booking_status": "pending",
                        },
                    ],
                }
            )
        else:
            route.fulfill(status=404)


@pytest.fixture
def transactions_app(page: Page) -> TransactionApp:
    app = TransactionApp()
    page.route("http://127.0.0.1:8765/**", app.serve)
    return app


def test_filters_paging_details_and_exact_amount(
    page: Page, transactions_app: TransactionApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("-92233720368547758.08 EUR", exact=True)).to_be_visible()
    expect(
        page.get_by_text("Booking status: unknown; reconciliation: unresolved")
    ).to_be_visible()
    page.get_by_role("button", name="View details").click()
    expect(
        page.get_by_text("Operation: <img src=x onerror=alert(1)>", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text("Bank suggestion: <b>Travel</b>", exact=True)
    ).to_be_visible()
    assert page.locator("#transaction-details img").count() == 0
    page.get_by_role("button", name="Next page").click()
    assert transactions_app.searches[-1]["cursor"] == "next"
    page.get_by_label("Description").fill("absent")
    page.get_by_label("Minimum amount (EUR)").fill("-5.00")
    page.get_by_label("Maximum amount (EUR)").fill("+9.99")
    page.get_by_label("From date").fill("2025-01-01")
    page.get_by_label("To date").fill("2025-01-31")
    page.get_by_label("Booking status").select_option("unknown")
    page.get_by_label("Bank-suggested category").select_option("value:Food")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_text("No transactions match", exact=False)).to_be_visible()
    assert transactions_app.searches[-1]["amount_min"] == "-5.00"
    assert transactions_app.searches[-1]["amount_max"] == "+9.99"
    assert transactions_app.searches[-1]["date_from"] == "2025-01-01"
    assert transactions_app.searches[-1]["date_to"] == "2025-01-31"
    assert transactions_app.searches[-1]["booking_status"] == "unknown"
    assert transactions_app.searches[-1]["category"] == {
        "kind": "value",
        "value": "Food",
    }
    assert "cursor" not in transactions_app.searches[-1]
    assert "absent" not in page.url
    page.get_by_role("button", name="Clear filters").click()
    expect(page.get_by_text("-92233720368547758.08 EUR", exact=True)).to_be_visible()
    page.get_by_label("Bank-suggested category").select_option("none")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_text("-92233720368547758.08 EUR", exact=True)).to_be_visible()
    assert transactions_app.searches[-1]["category"] == {"kind": "no_recorded_category"}


def test_empty_error_and_invalid_ranges(
    page: Page, transactions_app: TransactionApp
) -> None:
    transactions_app.empty_history = True
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("No recorded transactions", exact=False)).to_be_visible()
    transactions_app.empty_history = False
    transactions_app.fail_search = True
    page.get_by_role("button", name="Apply filters").click()
    expect(
        page.get_by_text("Could not retrieve transactions", exact=False)
    ).to_be_visible()
    transactions_app.fail_search = False
    page.get_by_role("button", name="Retry transactions").click()
    expect(page.get_by_text("-92233720368547758.08 EUR", exact=True)).to_be_visible()
    before = len(transactions_app.searches)
    page.get_by_label("From date").fill("2025-02-01")
    page.get_by_label("To date").fill("2025-01-01")
    page.get_by_role("button", name="Apply filters").click()
    expect(
        page.get_by_text("End date must not precede start date", exact=False)
    ).to_be_visible()
    assert len(transactions_app.searches) == before
    page.get_by_label("From date").fill("")
    page.get_by_label("To date").fill("")
    page.get_by_label("Minimum amount (EUR)").fill("1.234")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_text("at most two decimal places", exact=False)).to_be_visible()
    assert len(transactions_app.searches) == before
    page.get_by_role("button", name="Chat", exact=True).click()
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("at most two decimal places", exact=False)).to_be_visible()
    assert len(transactions_app.searches) == before


def test_timeout_is_retrieval_error(
    page: Page, transactions_app: TransactionApp
) -> None:
    transactions_app.stall_search = True
    page.clock.install()
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("Loading transactions...", exact=True)).to_be_visible()
    page.clock.fast_forward(75001)
    expect(
        page.get_by_text("Could not retrieve transactions", exact=False)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Retry transactions")).to_be_visible()


@pytest.mark.parametrize("label", ["From date", "To date"])
def test_incomplete_date_is_rejected_without_fetching(
    page: Page, transactions_app: TransactionApp, label: str
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("-92233720368547758.08 EUR", exact=True)).to_be_visible()
    before = len(transactions_app.searches)
    control = page.get_by_label(label)
    control.press_sequentially("02312025")
    assert control.evaluate("element => element.validity.badInput") is True
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_text("Enter a valid date", exact=False)).to_be_visible()
    assert len(transactions_app.searches) == before


def test_history_refreshes_after_import_without_restarting(
    page: Page, transactions_app: TransactionApp
) -> None:
    transactions_app.empty_history = True
    requested_urls: list[str] = []
    page.on("request", lambda request: requested_urls.append(request.url))
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("No recorded transactions", exact=False)).to_be_visible()
    page.get_by_role("button", name="Import transactions").click()
    page.get_by_label("Local folder").fill("/synthetic")
    page.get_by_role("button", name="Start import").click()
    expect(page.get_by_text("Import running", exact=False)).to_be_visible()
    transactions_app.empty_history = False
    assert transactions_app.run is not None
    own_id = transactions_app.run["id"]
    transactions_app.run = import_run("succeeded")
    transactions_app.run["id"] = own_id
    expect(page.get_by_text("Import completed", exact=False)).to_be_visible(
        timeout=5000
    )
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.get_by_text("-92233720368547758.08 EUR", exact=True)).to_be_visible()
    assert all(url.startswith("http://127.0.0.1:8765/") for url in requested_urls)
    assert all("/synthetic" not in url for url in requested_urls)
