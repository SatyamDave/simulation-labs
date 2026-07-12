"""execute_action: every ActionType maps to the right Playwright call.

All pages are data: URLs — no network, no API keys.
"""

from __future__ import annotations

import time

import pytest

import ghostpanel.runner.execute as execute_mod
from ghostpanel.runner.execute import WAIT_CAP_S, execute_action
from ghostpanel_contracts import Action, ActionType, ScrollDirection

TEST_PAGE = (
    "data:text/html,"
    "<body style='margin:0'>"
    "<button style='position:fixed;left:100px;top:100px;width:120px;height:40px'"
    " onclick='window.clicked=true'>Go</button>"
    "<input id='t' style='position:fixed;left:100px;top:200px;width:200px;height:30px'>"
    "<div style='height:3000px'></div>"
    "</body>"
)
OTHER_PAGE = "data:text/html,<h1>elsewhere</h1>"


async def test_click_lands_at_true_viewport_pixels(page):
    await page.goto(TEST_PAGE)
    action = Action(type=ActionType.CLICK, x=160, y=120, caption="Clicking Go")
    await execute_action(page, action)
    assert await page.evaluate("window.clicked === true")


async def test_click_without_coords_raises(page):
    await page.goto(TEST_PAGE)
    with pytest.raises(ValueError):
        await execute_action(page, Action(type=ActionType.CLICK, caption="bad click"))


async def test_write_clicks_types_and_presses_enter(page):
    await page.goto(TEST_PAGE)
    action = Action(type=ActionType.WRITE, x=200, y=215, text="hello world", caption="Typing")
    await execute_action(page, action)
    assert await page.evaluate("document.getElementById('t').value") == "hello world"


async def test_scroll_down_moves_the_page(page):
    await page.goto(TEST_PAGE)
    assert await page.evaluate("window.scrollY") == 0
    await execute_action(
        page, Action(type=ActionType.SCROLL, direction=ScrollDirection.DOWN, caption="Scroll")
    )
    await page.wait_for_function("window.scrollY > 0")


async def test_goto_go_back_and_refresh(page):
    await page.goto(TEST_PAGE)
    await execute_action(page, Action(type=ActionType.GOTO, url=OTHER_PAGE, caption="Goto"))
    assert page.url == OTHER_PAGE
    await execute_action(page, Action(type=ActionType.GO_BACK, caption="Back"))
    assert page.url == TEST_PAGE
    await execute_action(page, Action(type=ActionType.REFRESH, caption="Refresh"))
    assert page.url == TEST_PAGE


async def test_wait_sleeps_briefly(page):
    await page.goto(TEST_PAGE)
    t0 = time.monotonic()
    await execute_action(page, Action(type=ActionType.WAIT, seconds=0.2, caption="Wait"))
    assert 0.15 <= time.monotonic() - t0 < 5.0


async def test_wait_is_capped_at_ten_seconds(page, monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    await page.goto(TEST_PAGE)
    # Patch AFTER goto: playwright internals also call asyncio.sleep(0).
    monkeypatch.setattr(execute_mod.asyncio, "sleep", fake_sleep)
    await execute_action(page, Action(type=ActionType.WAIT, seconds=999, caption="Long wait"))
    assert WAIT_CAP_S in slept
    assert 999 not in slept and max(slept) == WAIT_CAP_S


async def test_restart_returns_to_session_start_url(page):
    await page.goto(TEST_PAGE)
    await page.goto(OTHER_PAGE)
    await execute_action(
        page, Action(type=ActionType.RESTART, caption="Restart"), target_url=TEST_PAGE
    )
    assert page.url == TEST_PAGE


async def test_restart_without_target_url_raises(page):
    await page.goto(TEST_PAGE)
    with pytest.raises(ValueError):
        await execute_action(page, Action(type=ActionType.RESTART, caption="Restart"))


async def test_answer_is_a_noop(page):
    await page.goto(TEST_PAGE)
    await execute_action(page, Action(type=ActionType.ANSWER, text="done", caption="Done"))
    assert page.url == TEST_PAGE
