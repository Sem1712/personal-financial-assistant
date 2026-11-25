"""Fixtures for browser tests using synthetic exports."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

from tests.fixtures.ui import create_export


@pytest.fixture
def page(pytestconfig: pytest.Config) -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=pytestconfig.getoption("--browser-channel")
        )
        try:
            yield browser.new_page()
        finally:
            browser.close()


@pytest.fixture
def export_directory(tmp_path: Path) -> Path:
    create_export(tmp_path)
    return tmp_path
