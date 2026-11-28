from playwright.sync_api import Page, expect

from tests.browser.test_transactions import TransactionApp


def test_context_is_separate_safe_and_read_only(page: Page) -> None:
    app = TransactionApp()
    app.enrichment.update(
        {
            "user_annotation": "<img src=x onerror=alert(1)>",
            "user_explanation": "User explanation",
            "ai_explanation": "<b>AI interpretation</b>",
        }
    )
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    expect(
        page.get_by_text("User annotation: <img src=x onerror=alert(1)>", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text("User explanation: User explanation", exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text("AI explanation: <b>AI interpretation</b>", exact=True)
    ).to_be_visible()
    assert (
        page.locator(
            "#transaction-details img, #transaction-details b, #transaction-details textarea, #transaction-details input"
        ).count()
        == 0
    )
    app.fail_detail = True
    page.get_by_role("button", name="Details", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    expect(
        page.get_by_text("Could not retrieve transaction details. Try again.")
    ).to_be_visible()
    app.fail_detail = False
    page.get_by_role("button", name="Retry details").click()
    expect(
        page.get_by_text("AI explanation: <b>AI interpretation</b>", exact=True)
    ).to_be_visible()


def test_missing_context_is_explicit(page: Page) -> None:
    app = TransactionApp()
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Transactions", exact=True).click()
    page.get_by_role("button", name="Details", exact=True).click()
    for label in ("User annotation", "User explanation", "AI explanation"):
        expect(page.get_by_text(f"{label}: Absent", exact=True)).to_be_visible()
