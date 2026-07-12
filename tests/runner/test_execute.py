"""execute_action lands real Playwright actions on a live page."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from ghostpanel.runner.execute import execute_action
from ghostpanel_contracts import Action, ActionType


@pytest.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 400, "height": 300})
        pg = await context.new_page()
        yield pg
        await context.close()
        await browser.close()


async def test_click_fires_handler(page):
    # A full-viewport target that flips a JS flag when clicked.
    await page.set_content(
        """
        <div id="hit" style="position:fixed;inset:0;"
             onclick="window.__clicked = {x: event.clientX, y: event.clientY};">
        </div>
        """
    )
    await execute_action(page, Action(type=ActionType.CLICK, x=200, y=150))
    clicked = await page.evaluate("() => window.__clicked || null")
    assert clicked is not None
    # Coordinates are executed verbatim (no rescaling).
    assert clicked["x"] == 200
    assert clicked["y"] == 150


async def test_write_types_text(page):
    await page.set_content('<input id="box" style="position:fixed;top:0;left:0;width:400px;height:60px;">')
    await execute_action(page, Action(type=ActionType.WRITE, x=10, y=20, text="hello"))
    value = await page.evaluate("() => document.getElementById('box').value")
    assert value == "hello"


async def test_scroll_moves_page(page):
    await page.set_content('<div style="height:3000px;">tall</div>')
    from ghostpanel_contracts import ScrollDirection

    await page.mouse.move(200, 150)
    await execute_action(page, Action(type=ActionType.SCROLL, direction=ScrollDirection.DOWN))
    await page.wait_for_function("() => window.scrollY > 0")
    y = await page.evaluate("() => window.scrollY")
    assert y > 0
