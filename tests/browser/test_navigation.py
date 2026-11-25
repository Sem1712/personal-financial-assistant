from playwright.sync_api import Page, expect

from tests.browser.test_import import LocalApp, import_run
from tests.browser.test_transactions import TransactionApp


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


def test_selected_navigation_focus_and_running_poll_stability(page: Page) -> None:
    app = LocalApp()
    page.clock.install()
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    chat = page.get_by_role("button", name="Chat", exact=True)
    expect(chat).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Import", exact=True).click()
    expect(page.locator("#import h2")).to_be_focused()
    current = page.get_by_role("button", name="Import", exact=True)
    expect(current).to_have_attribute("aria-current", "page")
    app.run = import_run("running")
    page.clock.fast_forward(1001)
    expect(page.locator("#import-start")).to_be_disabled()
    current.focus()
    page.clock.fast_forward(2001)
    expect(current).to_be_focused()
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(current).to_have_attribute("aria-current", "page")
    expect(page.locator("#transactions")).to_be_hidden()


def test_skip_link_and_narrow_shell(page: Page) -> None:
    app = LocalApp()
    page.set_viewport_size({"width": 320, "height": 800})
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Skip to main content")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main-content")).to_be_focused()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_focus_rings_and_placeholder_hints(page: Page) -> None:
    app = LocalApp()
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    page.get_by_role("button", name="Import", exact=True).click()
    heading = page.locator("#import-heading")
    expect(heading).to_be_focused()
    assert heading.evaluate("el => getComputedStyle(el).outlineStyle") == "none"
    page.locator("#import-status").evaluate(
        "el => { el.textContent = 'Loading'; el.focus(); }"
    )
    assert (
        page.locator("#import-status").evaluate(
            "el => getComputedStyle(el).outlineStyle"
        )
        == "none"
    )
    field = page.get_by_label("Local folder")
    field.focus()
    assert field.evaluate("el => getComputedStyle(el).outlineWidth") == "3px"
    styles = field.evaluate(
        """el => {
            const text = getComputedStyle(el);
            const hint = getComputedStyle(el, '::placeholder');
            return {
                textColor: text.color, hintColor: hint.color,
                textSize: parseFloat(text.fontSize), hintSize: parseFloat(hint.fontSize),
                hintStyle: hint.fontStyle
            };
        }"""
    )
    assert styles["textColor"] != styles["hintColor"]
    text_rgb = [int(value) for value in styles["textColor"][4:-1].split(",")]
    hint_rgb = [int(value) for value in styles["hintColor"][4:-1].split(",")]
    assert all(hint < text for hint, text in zip(hint_rgb, text_rgb, strict=True))
    assert styles["hintSize"] < styles["textSize"]
    assert styles["hintStyle"] == "italic"
    expect(field).to_have_attribute("placeholder", "e.g. /path/to/exports")
    field.fill("/synthetic")
    page.keyboard.press("Tab")
    button = page.get_by_role("button", name="Start import")
    expect(button).to_be_focused()
    assert button.evaluate("el => getComputedStyle(el).outlineWidth") == "3px"


def test_dark_theme_surfaces_and_text_contrast(page: Page) -> None:
    page.emulate_media(reduced_motion="reduce")
    app = TransactionApp()
    app.amount_minor = "1250"
    page.route("http://127.0.0.1:8765/**", app.serve)
    page.goto("http://127.0.0.1:8765/")
    expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")

    def luminance(color: str) -> float:
        channels = [
            int(value) / 255
            for value in color.removeprefix("rgb(").removesuffix(")").split(",")
        ]
        assert len(channels) == 3
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return sum(
            weight * value
            for weight, value in zip((0.2126, 0.7152, 0.0722), linear, strict=True)
        )

    def check_contrast(selectors: list[str]) -> None:
        samples = page.evaluate(
            """selectors => selectors.map(selector => {
                const [target, pseudo] = selector.split('::');
                const el = document.querySelector(target);
                const foreground = getComputedStyle(el, pseudo ? `::${pseudo}` : null).color;
                let parent = el;
                while (parent) {
                    const background = getComputedStyle(parent).backgroundColor;
                    if (background !== 'rgba(0, 0, 0, 0)') {
                        return {selector, foreground, background};
                    }
                    parent = parent.parentElement;
                }
                throw new Error(`No background for ${selector}`);
            })""",
            selectors,
        )
        for sample in samples:
            foreground = luminance(sample["foreground"])
            background = luminance(sample["background"])
            ratio = (max(foreground, background) + 0.05) / (
                min(foreground, background) + 0.05
            )
            assert ratio >= 4.5, sample["selector"]

    assert (
        luminance(
            page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
        )
        < 0.05
    )
    check_contrast(
        ["body", "h1", ".local-label", ".text-body-secondary", ".btn-primary"]
    )
    page.get_by_role("button", name="Import", exact=True).click()
    check_contrast(
        [
            ".navigation-button[aria-current]",
            "#import-folder",
            "#import-folder::placeholder",
            ".form-label",
        ]
    )
    for kind in ("loading", "successful", "unknown", "failed"):
        page.locator("#import-status").evaluate(
            """(el, kind) => {
                el.textContent = 'Synthetic status';
                el.dataset.kind = kind;
            }""",
            kind,
        )
        check_contrast(["#import-status"])
    page.get_by_role("button", name="Transactions", exact=True).click()
    expect(page.locator(".transaction-row")).to_have_count(1)
    page.get_by_text("Filter your records", exact=True).click()
    assert (
        page.locator("#date-from").evaluate("el => getComputedStyle(el).colorScheme")
        == "dark"
    )
    check_contrast(
        [
            ".transaction-operation",
            ".cell-label",
            ".transaction-toggle",
            "#description::placeholder",
            "#transaction-pages-top [data-page-action='next']",
        ]
    )
    page.get_by_role("button", name="Details", exact=True).click()
    expect(page.locator(".source-observation")).to_have_count(2)
    check_contrast(["#detail-context", ".source-observation p"])
