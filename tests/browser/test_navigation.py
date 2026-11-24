from playwright.sync_api import Page, expect

from tests.browser.test_import import LocalApp


def test_chat_is_initial_and_future_capabilities_are_unavailable(page: Page) -> None:
    app = LocalApp()
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    expect(page.get_by_role("heading", name="Chat")).to_be_visible()
    expect(page.get_by_text("Chat and reports are not available yet.")).to_be_visible()
    assert page.get_by_role("textbox", name="Message").count() == 0
    assert page.get_by_role("button", name="Send").count() == 0
    assert page.get_by_role("button", name="Create report").count() == 0
    page.get_by_role("button", name="Go to import").click()
    expect(page.get_by_role("heading", name="Import")).to_be_visible()
    page.get_by_role("button", name="Chat", exact=True).click()
    page.get_by_role("button", name="Go to transactions").click()
    expect(page.get_by_role("heading", name="Transactions")).to_be_visible()
