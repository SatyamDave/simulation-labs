"""Shared fixtures for runner tests: hermetic (file:// / data: pages only)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def hostile_form_url() -> str:
    return (FIXTURES_DIR / "hostile_form.html").as_uri()


@pytest_asyncio.fixture()
async def browser():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest_asyncio.fixture()
async def page(browser):
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()
    yield page
    await context.close()
