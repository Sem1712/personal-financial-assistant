import json
from itertools import pairwise
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
        self.fail_detail = False
        self.fail_categories = False
        self.multiple_occurrences = False
        self.amount_minor = "-9223372036854775808"
        self.currency = "EUR"
        self.operations = ["Synthetic purchase"]
        self.details = ["Synthetic recorded details"]
        self.detail_ids: list[str] = []
        self.run: dict[str, object] | None = None
        self.enrichment: dict[str, object] = {
            "transaction_type": {
                "value": "expense",
                "status": "confirmed",
                "source": "user",
                "confidence": None,
            },
            "category": {
                "value": "<b>Groceries</b>",
                "status": "provisional",
                "source": "ai",
                "confidence": "72.5",
            },
            "budget_treatment": {
                "value": "excluded",
                "status": "confirmed",
                "source": "rule",
                "confidence": None,
            },
            "user_annotation": None,
            "user_explanation": None,
            "ai_explanation": None,
        }

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
            if self.fail_categories:
                route.fulfill(status=503, json={"error": {"message": "Unavailable."}})
            else:
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
                        "amount_minor": self.amount_minor,
                        "currency": self.currency,
                        "booking_status": "unknown",
                        "reconciliation_state": "unresolved",
                        "ongoing_expense": False,
                        "operations": self.operations,
                        "details": self.details,
                    }
                ]
            )
            if items and self.multiple_occurrences and not body.get("cursor"):
                items.append({**items[0], "id": "2"})
            route.fulfill(
                json={
                    "items": items,
                    "next_cursor": "next" if items and not body.get("cursor") else None,
                    "history_exists": not self.empty_history,
                }
            )
        elif path == "/api/transactions/detail":
            requested_id = json.loads(request.post_data or "{}")["id"]
            self.detail_ids.append(requested_id)
            if self.fail_detail:
                route.fulfill(status=503, json={"error": {"message": "Unavailable."}})
                return
            route.fulfill(
                json={
                    "id": requested_id,
                    "date": "2025-01-15",
                    "amount_minor": "-9223372036854775808",
                    "currency": self.currency,
                    "booking_status": "unknown",
                    "reconciliation_state": "unresolved",
                    "ongoing_expense": False,
                    "enrichment": self.enrichment,
                    "observations": [
                        {
                            "operation": "<img src=x onerror=alert(1)>",
                            "details": self.details[0] if self.details else None,
                            "category": "Food",
                            "booking_status": "booked",
                        },
                        {
                            "operation": "Other",
                            "details": f"Evidence for record {requested_id}",
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
    expect(page.locator(".transaction-operation")).to_have_text("Synthetic purchase")
    expect(
        page.get_by_text("Booking status: unknown; reconciliation: unresolved")
    ).to_be_hidden()
    expect(page.get_by_text("Category: <b>Groceries</b>", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Details", exact=True).click()
    expect(
        page.get_by_text("Booking status: unknown; reconciliation: unresolved")
    ).to_be_visible()
    expect(
        page.get_by_text("Operation: <img src=x onerror=alert(1)>", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text("Bank suggestion: <b>Travel</b>", exact=True)
    ).to_be_visible()
    expect(page.get_by_text("Category: <b>Groceries</b>", exact=True)).to_be_visible()
    expect(page.get_by_text("Transaction type: expense", exact=True)).to_be_visible()
    expect(page.get_by_text("Budget treatment: excluded", exact=True)).to_be_visible()
    expect(page.get_by_text("Source: ai", exact=True)).to_be_visible()
    expect(page.get_by_text("Confidence: 72.5%", exact=True)).to_be_visible()
    expect(
        page.get_by_text("Confidence: Unavailable", exact=True).first
    ).to_be_visible()
    assert (
        page.locator(
            "#transaction-details input, #transaction-details textarea"
        ).count()
        == 0
    )
    assert page.locator("#transaction-details img").count() == 0
    page.get_by_role("button", name="Next page").first.click()
    assert transactions_app.searches[-1]["cursor"] == "next"
    page.get_by_text("Filter your records", exact=True).click()
    page.get_by_label("Description").fill("absent")
    page.get_by_label("Minimum absolute amount (EUR)").fill("5.00")
    page.get_by_label("Maximum absolute amount (EUR)").fill("+9.99")
    page.get_by_label("Transaction type").select_option("withdrawals")
    page.get_by_label("From date").fill("2025-01-01")
    page.get_by_label("To date").fill("2025-01-31")
    page.get_by_label("Booking status").select_option("unknown")
    page.get_by_label("Bank-suggested category").select_option("value:Food")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_text("No transactions match", exact=False)).to_be_visible()
    assert transactions_app.searches[-1]["amount_min"] == "5.00"
    assert transactions_app.searches[-1]["amount_max"] == "+9.99"
    assert transactions_app.searches[-1]["direction"] == "withdrawals"
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
    assert "direction" not in transactions_app.searches[-1]
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
    page.get_by_text("Filter your records", exact=True).click()
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
    page.get_by_label("Minimum absolute amount (EUR)").fill("1.234")
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
    page.get_by_text("Filter your records", exact=True).click()
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


@pytest.mark.parametrize("width", [320, 1440])
def test_filter_accordion_preserves_drafts_and_applied_query(
    page: Page, transactions_app: TransactionApp, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    form = page.locator("#transaction-filters")
    toggle = page.locator("#transaction-filter-panel > summary")
    expect(form).to_be_hidden()
    before = len(transactions_app.searches)
    toggle.focus()
    page.keyboard.press("Enter")
    expect(form).to_be_visible()
    assert len(transactions_app.searches) == before
    page.get_by_label("Description").fill("Evidence")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator("#filters-summary")).to_contain_text("Evidence")
    page.get_by_label("Description").fill("Not applied")
    before = len(transactions_app.searches)
    toggle.focus()
    page.keyboard.press("Space")
    expect(form).to_be_hidden()
    expect(toggle).to_be_focused()
    assert toggle.evaluate("el => getComputedStyle(el).outlineWidth") == "3px"
    assert len(transactions_app.searches) == before
    expect(page.locator("#filters-summary")).to_be_visible()
    expect(page.locator("#filters-summary")).not_to_contain_text("Not applied")
    page.get_by_role("button", name="Next page").first.click()
    expect(page.locator('[data-occurrence-id="2"]')).to_be_visible()
    assert transactions_app.searches[-1]["text"] == "Evidence"
    toggle.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_label("Description")).to_have_value("Not applied")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("width", [320, 768, 1440])
def test_amount_controls_share_the_second_filter_row(
    page: Page, transactions_app: TransactionApp, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    bounds = page.evaluate(
        """() => ['date-from', 'date-to', 'booking-status', 'transaction-direction',
                  'amount-min', 'amount-max', 'description', 'category'].map(id => {
            const rect = document.getElementById(id).getBoundingClientRect();
            return {x: rect.x, y: rect.y, bottom: rect.bottom};
        })"""
    )
    if width >= 768:
        assert (
            max(item["y"] for item in bounds[:3])
            - min(item["y"] for item in bounds[:3])
            < 1
        )
        assert (
            max(item["y"] for item in bounds[3:6])
            - min(item["y"] for item in bounds[3:6])
            < 1
        )
        assert bounds[3]["y"] > max(item["bottom"] for item in bounds[:3])
        assert bounds[6]["y"] > max(item["bottom"] for item in bounds[3:6])
        assert bounds[3]["x"] < bounds[4]["x"] < bounds[5]["x"]
    else:
        assert all(
            current["bottom"] < following["y"]
            for current, following in pairwise(bounds)
        )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_applied_filter_summary_does_not_follow_drafts(
    page: Page, transactions_app: TransactionApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    page.get_by_label("Description").fill("Evidence")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator("#filters-summary")).to_contain_text("Evidence")
    page.get_by_label("Description").fill("Not applied")
    page.get_by_role("button", name="Next page").first.click()
    expect(page.locator("#filters-summary")).to_contain_text("Evidence")
    expect(page.locator("#filters-summary")).not_to_contain_text("Not applied")
    assert transactions_app.searches[-1]["text"] == "Evidence"
    page.get_by_label("Minimum absolute amount (EUR)").fill("1.234")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_label("Minimum absolute amount (EUR)")).to_have_attribute(
        "aria-invalid", "true"
    )
    expect(page.get_by_label("Minimum absolute amount (EUR)")).to_have_attribute(
        "aria-describedby", "filter-error"
    )
    expect(page.locator("#transaction-list article")).to_have_count(0)
    page.get_by_role("button", name="Clear filters").click()
    expect(page.locator("#filters-summary")).to_have_text("All recorded transactions")


def test_detail_failure_retry_and_close_keep_identity_and_focus(
    page: Page, transactions_app: TransactionApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Next page").first.click()
    transactions_app.fail_detail = True
    initiating = page.get_by_role("button", name="Details", exact=True)
    initiating.click()
    expect(initiating).to_be_focused()
    expect(page.locator("#detail-context")).to_contain_text("Record 2")
    expect(page.get_by_role("button", name="Retry details")).to_be_visible()
    transactions_app.fail_detail = False
    page.get_by_role("button", name="Retry details").click()
    expect(page.get_by_text("Operation: Other", exact=True)).to_be_visible()
    assert transactions_app.detail_ids == ["2", "2"]
    initiating.click()
    expect(page.locator("#transaction-details")).to_be_hidden()
    expect(initiating).to_be_focused()


@pytest.mark.parametrize("action", ["toggle", "page", "filter", "navigation"])
def test_superseded_details_ignore_pending_response(
    page: Page, transactions_app: TransactionApp, action: str
) -> None:
    pending: list[Route] = []
    page.route("**/api/transactions/detail", lambda route: pending.append(route))
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    expect(
        page.get_by_text("Loading transaction details...", exact=True)
    ).to_be_visible()
    if action == "toggle":
        page.get_by_role("button", name="Details", exact=True).click()
    elif action == "page":
        page.get_by_role("button", name="Next page").first.click()
    elif action == "filter":
        page.get_by_text("Filter your records", exact=True).click()
        page.get_by_label("Description").fill("absent")
        page.get_by_role("button", name="Apply filters").click()
    else:
        page.get_by_role("button", name="Chat", exact=True).click()
        expect(page.get_by_role("heading", name="Chat")).to_be_visible()
    assert len(pending) == 1
    with page.expect_response("**/api/transactions/detail") as response:
        transactions_app.serve(pending[0])
    response.value.finished()
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 0))")
    expect(page.locator("#transaction-details")).to_be_hidden()
    expect(page.locator("#detail-observations")).to_be_empty()


@pytest.mark.parametrize("label", ["From date", "To date"])
def test_unsupported_date_year_is_associated_without_search(
    page: Page, transactions_app: TransactionApp, label: str
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    before = len(transactions_app.searches)
    control = page.get_by_label(label)
    control.fill("10000-01-01")
    page.get_by_role("button", name="Apply filters").click()
    expect(control).to_have_value("10000-01-01")
    expect(control).to_have_attribute("aria-invalid", "true")
    expect(control).to_have_attribute("aria-describedby", "filter-error")
    expect(page.locator("#filter-error")).to_contain_text("0001")
    expect(page.locator("#transaction-list")).to_be_empty()
    assert len(transactions_app.searches) == before
    page.get_by_label("From date").fill("0001-01-01")
    page.get_by_label("To date").fill("9999-12-31")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    assert transactions_app.searches[-1]["date_from"] == "0001-01-01"
    assert transactions_app.searches[-1]["date_to"] == "9999-12-31"


def test_keyboard_paging_keeps_focus_at_results_on_boundaries(
    page: Page, transactions_app: TransactionApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Next page").first.focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-occurrence-id="2"]')).to_be_visible()
    expect(page.locator("#transaction-status")).to_be_focused()
    page.get_by_role("button", name="Previous page").first.focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-occurrence-id="9223372036854775807"]')).to_be_visible()
    expect(page.locator("#transaction-status")).to_be_focused()


@pytest.mark.parametrize("operation", ["transactions", "categories"])
@pytest.mark.parametrize("succeeds", [False, True])
def test_keyboard_retry_keeps_focus_and_category_failure_allows_filters(
    page: Page, transactions_app: TransactionApp, operation: str, succeeds: bool
) -> None:
    failure_flag = "fail_search" if operation == "transactions" else "fail_categories"
    setattr(transactions_app, failure_flag, True)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    retry = page.locator(
        "#transaction-retry" if operation == "transactions" else "#category-retry"
    )
    if operation == "categories":
        page.get_by_text("Filter your records", exact=True).click()
    expect(retry).to_be_visible()
    if operation == "categories":
        page.get_by_label("Description").fill("Evidence")
        page.get_by_role("button", name="Apply filters").click()
        expect(page.locator(".transaction-row")).to_have_count(1)
        assert transactions_app.searches[-1]["text"] == "Evidence"
        expect(page.locator("#category-status")).to_contain_text(
            "Could not retrieve bank-suggested categories."
        )
    setattr(transactions_app, failure_flag, not succeeds)
    retry.focus()
    page.keyboard.press("Enter")
    if not succeeds:
        expect(retry).to_be_visible()
        expect(retry).to_be_focused()
    else:
        expect(retry).to_be_hidden()
        expect(
            page.locator(
                "#transaction-status" if operation == "transactions" else "#category"
            )
        ).to_be_focused()
        if operation == "categories":
            expect(page.locator("#category-status")).to_have_text("")
            expect(page.locator("#category option[value='value:Food']")).to_have_count(
                1
            )


def test_paging_response_does_not_take_focus_after_user_moves(
    page: Page, transactions_app: TransactionApp
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    results_height = page.locator("#transaction-list").evaluate(
        "el => el.getBoundingClientRect().height"
    )
    pending: list[Route] = []
    page.route("**/api/transactions/search", lambda route: pending.append(route))
    page.get_by_role("button", name="Next page").first.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#transaction-status")).to_be_focused()
    expect(page.locator("#transaction-list")).to_have_attribute("aria-busy", "true")
    assert page.locator("#transaction-list").evaluate("el => el.inert") is True
    assert (
        page.locator("#transaction-list").evaluate(
            "el => el.getBoundingClientRect().height"
        )
        == results_height
    )
    for control in page.locator("[data-page-action]").all():
        expect(control).to_be_visible()
        expect(control).to_be_disabled()
    description = page.get_by_label("Description")
    description.focus()
    assert len(pending) == 1
    transactions_app.serve(pending[0])
    expect(page.locator('[data-occurrence-id="2"]')).to_be_visible()
    expect(description).to_be_focused()
    expect(page.locator("#transaction-list")).to_have_attribute("aria-busy", "false")
    assert page.locator("#transaction-list").evaluate("el => el.inert") is False


def test_competing_identical_occurrences_keep_latest_selected_evidence(
    page: Page, transactions_app: TransactionApp
) -> None:
    transactions_app.multiple_occurrences = True
    pending: list[Route] = []
    page.route("**/api/transactions/detail", lambda route: pending.append(route))
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    buttons = page.get_by_role("button", name="Details", exact=True)
    expect(buttons).to_have_count(2)
    buttons.nth(0).click()
    expect(page.locator("#detail-status")).to_contain_text("Loading")
    expect(
        page.locator(".transaction-row").nth(0).locator("#transaction-details")
    ).to_be_visible()
    buttons.nth(1).click()
    expect(buttons.nth(0)).to_have_attribute("aria-expanded", "false")
    expect(buttons.nth(1)).to_have_attribute("aria-expanded", "true")
    expect(
        page.locator(".transaction-row").nth(1).locator("#transaction-details")
    ).to_be_visible()
    expect(page.locator("#detail-context")).to_contain_text("Record 2")
    assert len(pending) == 2
    transactions_app.serve(pending[1])
    expect(
        page.get_by_text("Details: Evidence for record 2", exact=True)
    ).to_be_visible()
    with page.expect_response("**/api/transactions/detail") as response:
        transactions_app.serve(pending[0])
    response.value.finished()
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 0))")
    expect(page.locator("#detail-context")).to_contain_text("Record 2")
    expect(
        page.get_by_text("Details: Evidence for record 2", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text("Details: Evidence for record 9223372036854775807", exact=True)
    ).to_be_hidden()


@pytest.mark.parametrize("width", [320, 1440])
def test_details_expand_beneath_selected_row_and_toggle(
    page: Page, transactions_app: TransactionApp, width: int
) -> None:
    transactions_app.multiple_occurrences = True
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    rows = page.locator(".transaction-row")
    first = rows.nth(0)
    button = first.get_by_role("button", name="Details", exact=True)
    button.click()
    panel = first.locator("#transaction-details")
    expect(panel).to_be_visible()
    expect(button).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_text("Operation: Other", exact=True)).to_be_visible()
    bounds = panel.bounding_box()
    button_bounds = button.bounding_box()
    next_bounds = rows.nth(1).bounding_box()
    assert bounds is not None and button_bounds is not None and next_bounds is not None
    assert bounds["y"] >= button_bounds["y"] + button_bounds["height"]
    assert bounds["y"] + bounds["height"] <= next_bounds["y"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    button.click()
    expect(page.locator("#transaction-details")).to_be_hidden()
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(button).to_be_focused()
    assert len(transactions_app.detail_ids) == 1
    button.click()
    expect(panel).to_be_visible()
    page.get_by_role("button", name="Next page").first.click()
    expect(page.locator("#transaction-details")).to_be_hidden()
    expect(rows).to_have_count(1)
    page.get_by_role("button", name="Details", exact=True).click()
    expect(page.locator(".transaction-row #transaction-details")).to_be_visible()
    expect(page.locator("#detail-context")).to_contain_text("Record 2")


def test_mismatched_detail_response_retains_context_for_retry(
    page: Page, transactions_app: TransactionApp
) -> None:
    def mismatched(route: Route) -> None:
        route.fulfill(json={"id": "2", "observations": [{"operation": "Wrong record"}]})

    page.route("**/api/transactions/detail", mismatched)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    expect(page.locator("#detail-context")).to_contain_text(
        "Record 9223372036854775807"
    )
    expect(page.get_by_role("button", name="Retry details")).to_be_visible()
    expect(page.locator("#detail-observations")).to_be_empty()
    page.unroute("**/api/transactions/detail", mismatched)
    page.get_by_role("button", name="Retry details").click()
    expect(
        page.get_by_text("Details: Evidence for record 9223372036854775807", exact=True)
    ).to_be_visible()
    assert transactions_app.detail_ids == ["9223372036854775807"]


@pytest.mark.parametrize(
    ("minor", "currency", "direction", "highlight"),
    [
        ("9223372036854775807", "EUR", "positive", "green"),
        ("-9223372036854775808", "EUR", "negative", "red"),
        ("-9996", "EUR", "negative", "red"),
        ("-9995", "EUR", "negative", "red"),
        ("-9994", "EUR", "negative", "neutral"),
        ("9995", "EUR", "positive", "green"),
        ("0", "EUR", "neutral", "neutral"),
        ("-9995", "USD", "negative", "neutral"),
    ],
)
def test_signed_amount_card_borders(
    page: Page,
    transactions_app: TransactionApp,
    minor: str,
    currency: str,
    direction: str,
    highlight: str,
) -> None:
    transactions_app.amount_minor = minor
    transactions_app.currency = currency
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    row = page.locator(".transaction-row")
    expect(row).to_have_attribute("data-direction", direction)
    color = row.evaluate("el => getComputedStyle(el).borderTopColor")
    assert row.evaluate("el => getComputedStyle(el).borderTopWidth") == "2px"
    red, green, _ = [int(value) for value in color[4:-1].split(",")]
    if highlight == "green":
        assert green > red
    elif highlight == "red":
        assert red > green
    else:
        assert color == page.locator("#transactions .workspace-card").evaluate(
            "el => getComputedStyle(el).borderTopColor"
        )


@pytest.mark.parametrize("operations", [[], ["<img src=x>", "Different source"]])
def test_operations_are_primary_safe_text_with_one_toggle(
    page: Page, transactions_app: TransactionApp, operations: list[str]
) -> None:
    transactions_app.operations = operations
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    row = page.locator(".transaction-row")
    expect(row.locator(".transaction-operation")).to_have_text(
        "\n".join(operations) if operations else "Operation unavailable"
    )
    assert row.locator("img").count() == 0
    expect(row.get_by_role("button")).to_have_count(1)
    toggle = row.get_by_role("button", name="Details", exact=True)
    toggle.focus()
    page.keyboard.press("Enter")
    expect(toggle).to_be_focused()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    assert page.get_by_role("button", name="Close details").count() == 0
    page.keyboard.press("Enter")
    expect(page.locator("#transaction-details")).to_be_hidden()
    expect(toggle).to_be_focused()


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize(
    "details",
    [[], ["<img src=x>", "Different source details"], ["Long source details " * 80]],
)
def test_recorded_details_are_secondary_safe_text_without_extra_requests(
    page: Page, transactions_app: TransactionApp, details: list[str], width: int
) -> None:
    transactions_app.details = details
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    row = page.locator(".transaction-row")
    text = row.locator(".transaction-source-details")
    expect(text).to_have_text("; ".join(details) if details else "Details unavailable")
    assert row.locator("img").count() == 0
    assert transactions_app.detail_ids == []
    styles = text.evaluate(
        """el => ({
            size: parseFloat(getComputedStyle(el).fontSize),
            operationSize: parseFloat(getComputedStyle(el.previousElementSibling).fontSize),
            color: getComputedStyle(el).color,
            operationColor: getComputedStyle(el.previousElementSibling).color,
            height: el.getBoundingClientRect().height,
            lineHeight: parseFloat(getComputedStyle(el).lineHeight),
            ellipsis: getComputedStyle(el).textOverflow,
            overflowing: el.scrollWidth > el.clientWidth
        })"""
    )
    assert styles["size"] < styles["operationSize"]
    assert styles["color"] != styles["operationColor"]
    assert styles["height"] <= styles["lineHeight"] + 1
    assert styles["ellipsis"] == "ellipsis"
    if details and len(details[0]) > 100:
        assert styles["overflowing"]
        row.get_by_role("button", name="Details", exact=True).click()
        expect(page.locator("#detail-observations")).to_contain_text(details[0].strip())
    assert text.evaluate(
        "el => el.getBoundingClientRect().top >= el.previousElementSibling.getBoundingClientRect().bottom"
    )


@pytest.mark.parametrize("invalid", ["-0.01", "92233720368547758.09"])
def test_absolute_amount_filters_reject_negative_and_out_of_range_bounds(
    page: Page, transactions_app: TransactionApp, invalid: str
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    before = len(transactions_app.searches)
    page.get_by_label("Minimum absolute amount (EUR)").fill(invalid)
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator("#amount-min")).to_have_attribute("aria-invalid", "true")
    assert len(transactions_app.searches) == before
    page.get_by_role("button", name="Clear filters").click()
    expect(page.locator("#amount-min")).to_have_attribute(
        "aria-describedby", "amount-help"
    )
    page.get_by_label("Minimum absolute amount (EUR)").fill("92233720368547758.08")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    assert transactions_app.searches[-1]["amount_min"] == "92233720368547758.08"


@pytest.mark.parametrize("direction", ["", "withdrawals", "deposits"])
def test_direction_and_absolute_bounds_survive_paging_and_clear(
    page: Page, transactions_app: TransactionApp, direction: str
) -> None:
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    page.get_by_label("Transaction type").select_option(direction)
    page.get_by_label("Minimum absolute amount (EUR)").fill("0")
    page.get_by_label("Maximum absolute amount (EUR)").fill("50")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    page.get_by_role("button", name="Next page").first.click()
    expect(page.locator('[data-occurrence-id="2"]')).to_be_visible()
    assert transactions_app.searches[-1]["amount_min"] == "0"
    assert transactions_app.searches[-1]["amount_max"] == "50"
    assert transactions_app.searches[-1].get("direction") == (direction or None)
    page.get_by_role("button", name="Clear filters").click()
    expect(page.locator("#transaction-direction")).to_have_value("")
    expect(page.locator("#filters-summary")).to_have_text("All recorded transactions")
    assert transactions_app.searches[-1] == {}


def test_deposits_filter_suppresses_green_only_for_applied_criteria(
    page: Page, transactions_app: TransactionApp
) -> None:
    transactions_app.amount_minor = "1000"
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    row = page.locator(".transaction-row")
    expect(row).to_have_attribute("data-highlight", "positive")
    green = row.evaluate("el => getComputedStyle(el).borderTopColor")
    neutral = page.locator("#transactions .workspace-card").evaluate(
        "el => getComputedStyle(el).borderTopColor"
    )
    assert green != neutral
    page.get_by_text("Filter your records", exact=True).click()
    page.get_by_label("Transaction type").select_option("deposits")
    assert row.evaluate("el => getComputedStyle(el).borderTopColor") == green
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator("#filters-summary")).to_contain_text("Deposits")
    expect(row).to_have_attribute("data-direction", "positive")
    assert row.evaluate("el => getComputedStyle(el).borderTopColor") == neutral
    page.get_by_label("Transaction type").select_option("")
    assert row.evaluate("el => getComputedStyle(el).borderTopColor") == neutral
    page.get_by_role("button", name="Next page").first.click()
    expect(page.locator('[data-occurrence-id="2"]')).to_be_visible()
    assert transactions_app.searches[-1]["direction"] == "deposits"
    assert row.evaluate("el => getComputedStyle(el).borderTopColor") == neutral
    page.get_by_role("button", name="Clear filters").click()
    expect(row).to_have_attribute("data-highlight", "positive")
    assert row.evaluate("el => getComputedStyle(el).borderTopColor") == green


def test_pagination_is_mirrored_centered_and_positions_top_controls(
    page: Page, transactions_app: TransactionApp
) -> None:
    transactions_app.multiple_occurrences = True
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 1440, "height": 250})
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_text("Filter your records", exact=True).click()
    page.get_by_label("Description").fill("Evidence")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator(".transaction-row")).to_have_count(2)
    for navigation in page.locator(".transaction-pagination").all():
        expect(navigation.get_by_role("button")).to_have_count(3)
        expect(navigation.get_by_role("button", name="First page")).to_be_disabled()
        expect(navigation.get_by_role("button", name="Previous page")).to_be_disabled()
        expect(navigation.get_by_role("button", name="Next page")).to_be_enabled()
        assert navigation.evaluate(
            """el => {
                const container = el.getBoundingClientRect();
                const links = el.querySelector('ul').getBoundingClientRect();
                return Math.abs(links.x + links.width / 2 - container.x - container.width / 2) < 1;
            }"""
        )
        appearance = navigation.evaluate(
            """el => {
                const [first, previous, next] = el.querySelectorAll('button');
                const a = first.getBoundingClientRect();
                const b = previous.getBoundingClientRect();
                const c = next.getBoundingClientRect();
                return {
                    firstGap: b.x - a.right,
                    pairGap: c.x - b.right,
                    disabledBackground: getComputedStyle(first).backgroundColor,
                    enabledBackground: getComputedStyle(next).backgroundColor,
                    disabledCursor: getComputedStyle(first).cursor
                };
            }"""
        )
        assert appearance["firstGap"] >= 12
        assert abs(appearance["pairGap"]) <= 1
        assert appearance["disabledBackground"] != appearance["enabledBackground"]
        assert appearance["disabledCursor"] == "not-allowed"
    bottom_next = page.get_by_role("button", name="Next page").last
    bottom_next.scroll_into_view_if_needed()
    assert page.evaluate("window.scrollY") > 0
    bottom_next.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".transaction-row")).to_have_count(1)
    page.wait_for_function(
        """() => {
            const bounds = document.querySelector('#transaction-pages-top').getBoundingClientRect();
            return bounds.top >= 0 && bounds.bottom <= window.innerHeight;
        }"""
    )
    expect(page.locator("#transaction-status")).to_be_focused()
    for control in page.get_by_role("button", name="Next page").all():
        expect(control).to_be_visible()
        expect(control).to_be_disabled()
    for control in page.get_by_role("button", name="First page").all():
        expect(control).to_be_enabled()
    bottom_first = page.get_by_role("button", name="First page").last
    bottom_first.scroll_into_view_if_needed()
    bottom_first.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".transaction-row")).to_have_count(2)
    page.wait_for_function(
        """() => {
            const bounds = document.querySelector('#transaction-pages-top').getBoundingClientRect();
            return bounds.top >= 0 && bounds.bottom <= window.innerHeight;
        }"""
    )
    assert transactions_app.searches[-1] == {"text": "Evidence"}
    for control in page.get_by_role("button", name="Previous page").all():
        expect(control).to_be_disabled()
    top_next = page.get_by_role("button", name="Next page").first
    top_next.focus()
    previous_scroll = page.evaluate("window.scrollY")
    page.keyboard.press("Enter")
    expect(page.locator(".transaction-row")).to_have_count(1)
    page.wait_for_function(
        """previous => window.scrollY === Math.min(
            previous, document.documentElement.scrollHeight - window.innerHeight
        )""",
        arg=previous_scroll,
    )
    bottom_previous = page.get_by_role("button", name="Previous page").last
    bottom_previous.scroll_into_view_if_needed()
    bottom_previous.click()
    expect(page.locator(".transaction-row")).to_have_count(2)
    page.wait_for_function(
        """() => {
            const bounds = document.querySelector('#transaction-pages-top').getBoundingClientRect();
            return bounds.top >= 0 && bounds.bottom <= window.innerHeight;
        }"""
    )


@pytest.mark.parametrize("state", ["empty_history", "fail_search"])
def test_pagination_remains_visible_when_no_page_is_available(
    page: Page, transactions_app: TransactionApp, state: str
) -> None:
    setattr(transactions_app, state, True)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.locator("#transaction-status")).to_contain_text(
        "No recorded transactions"
        if state == "empty_history"
        else "Could not retrieve transactions"
    )
    controls = page.locator("[data-page-action]")
    expect(controls).to_have_count(6)
    for control in controls.all():
        expect(control).to_be_visible()
        expect(control).to_be_disabled()


@pytest.mark.parametrize(
    ("preference", "behavior"),
    [("no-preference", "smooth"), ("reduce", "instant")],
)
def test_bottom_pagination_respects_motion_preferences(
    page: Page, transactions_app: TransactionApp, preference: str, behavior: str
) -> None:
    transactions_app.multiple_occurrences = True
    page.set_viewport_size({"width": 1440, "height": 250})
    if preference == "reduce":
        page.emulate_media(reduced_motion="reduce")
    else:
        page.emulate_media(reduced_motion="no-preference")
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.locator(".transaction-row")).to_have_count(2)
    page.evaluate(
        """() => {
            window.paginationScrolls = [];
            const scroll = window.scrollTo.bind(window);
            window.scrollTo = options => {
                window.paginationScrolls.push(options);
                scroll(options);
            };
        }"""
    )
    bottom_next = page.get_by_role("button", name="Next page").last
    bottom_next.scroll_into_view_if_needed()
    bottom_next.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".transaction-row")).to_have_count(1)
    page.wait_for_function("window.paginationScrolls.length === 1")
    options = page.evaluate("window.paginationScrolls[0]")
    assert options["behavior"] == behavior
    page.wait_for_function(
        """() => {
            const bounds = document.querySelector('#transaction-pages-top').getBoundingClientRect();
            return bounds.top >= 0 && bounds.bottom <= window.innerHeight;
        }"""
    )
