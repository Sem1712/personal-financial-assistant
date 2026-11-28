import json

import pytest
from playwright.sync_api import Page, Route, expect

from tests.browser.test_transactions import TransactionApp


def test_mixed_provenance_and_invalid_response(page: Page) -> None:
    app = TransactionApp()
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    for source in ("user", "ai", "rule"):
        expect(page.get_by_text(f"Source: {source}", exact=True)).to_be_visible()
    expect(page.get_by_text("Status: provisional", exact=True)).to_be_visible()
    expect(page.get_by_text("Confidence: 72.5%", exact=True)).to_be_visible()
    expect(
        page.get_by_text("Bank suggestion: <b>Travel</b>", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text(
            "Excluded is intended for future budget exclusion; no budget has been calculated.",
            exact=True,
        )
    ).to_be_visible()
    assert page.locator("#transaction-details b").count() == 0
    page.get_by_role("button", name="Details", exact=True).click()
    app.enrichment["category"] = {"status": "confirmed"}
    page.get_by_role("button", name="Details", exact=True).click()
    expect(
        page.get_by_text("Could not retrieve transaction details. Try again.")
    ).to_be_visible()
    expect(page.get_by_text("Category: Unclassified", exact=True)).to_have_count(0)


@pytest.mark.parametrize("category", ["\ufeff", "🛒 groceries"])
def test_unicode_category_accepted_by_backend_is_displayed(
    page: Page, category: str
) -> None:
    app = TransactionApp()
    app.enrichment["category"] = {
        "value": category,
        "status": "confirmed",
        "source": "user",
        "confidence": None,
    }
    page.route("http://127.0.0.1:8765/**", app.serve)

    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    page.wait_for_function(
        """value => [...document.querySelectorAll('#detail-observations p')]
            .some(element => element.textContent === value)""",
        arg=f"Category: {category}",
    )
    expect(
        page.get_by_text("Could not retrieve transaction details. Try again.")
    ).to_have_count(0)


@pytest.mark.parametrize("category", ["\x85", "groceries\x00", "\ud800"])
def test_invalid_category_is_rejected(page: Page, category: str) -> None:
    app = TransactionApp()
    app.enrichment["category"] = {
        "value": category,
        "status": "confirmed",
        "source": "user",
        "confidence": None,
    }
    page.route("http://127.0.0.1:8765/**", app.serve)

    def detail(route: Route) -> None:
        route.fulfill(
            content_type="application/json",
            body=json.dumps(
                {
                    "id": "9223372036854775807",
                    "enrichment": app.enrichment,
                    "observations": [],
                }
            ),
        )

    page.route("http://127.0.0.1:8765/api/transactions/detail", detail)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    expect(
        page.get_by_text("Could not retrieve transaction details. Try again.")
    ).to_be_visible()
