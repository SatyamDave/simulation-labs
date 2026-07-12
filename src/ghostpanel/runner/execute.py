"""execute_action — map a decoded `Action` onto Playwright page calls.

COORDINATE GOLDEN RULE: `action.x` / `action.y` are already TRUE viewport pixels
(the engine applied tremor jitter + any smart_resize remap). Execute them verbatim
with `page.mouse.click(x, y)`. NEVER rescale.
"""

from __future__ import annotations

import asyncio

from ghostpanel_contracts import Action, ActionType, ScrollDirection

# How many pixels one SCROLL action moves the wheel.
_SCROLL_STEP = 600
# WaitAction is clamped to this many seconds (matches Holo's 0-10 range).
_MAX_WAIT_S = 10.0


def _scroll_delta(direction: ScrollDirection | None) -> tuple[int, int]:
    """Return (dx, dy) wheel deltas for a scroll direction (default: down)."""
    if direction == ScrollDirection.UP:
        return (0, -_SCROLL_STEP)
    if direction == ScrollDirection.LEFT:
        return (-_SCROLL_STEP, 0)
    if direction == ScrollDirection.RIGHT:
        return (_SCROLL_STEP, 0)
    # DOWN or unspecified
    return (0, _SCROLL_STEP)


async def execute_action(page, action: Action) -> None:
    """Perform `action` against the live Playwright `page`.

    ANSWER is a no-op here — the run loop interprets it as "persona declares done".
    RESTART requires the session's start URL, which the runner supplies via
    `action.url` (the runner rewrites RESTART into a GOTO of the start url before
    calling, but we also honor a bare RESTART by reloading as a safe fallback).
    """
    t = action.type

    if t == ActionType.CLICK:
        if action.x is not None and action.y is not None:
            await page.mouse.click(action.x, action.y)
        return

    if t == ActionType.WRITE:
        # Click the target first to focus it, then type. Holo's WriteElementAction
        # semantics submit with Enter.
        if action.x is not None and action.y is not None:
            await page.mouse.click(action.x, action.y)
        if action.text:
            await page.keyboard.type(action.text)
        await page.keyboard.press("Enter")
        return

    if t == ActionType.SCROLL:
        dx, dy = _scroll_delta(action.direction)
        await page.mouse.wheel(dx, dy)
        return

    if t == ActionType.GO_BACK:
        await page.go_back()
        return

    if t == ActionType.REFRESH:
        await page.reload()
        return

    if t == ActionType.GOTO:
        if action.url:
            await page.goto(action.url)
        return

    if t == ActionType.WAIT:
        secs = action.seconds if action.seconds is not None else 2.0
        await asyncio.sleep(min(max(secs, 0.0), _MAX_WAIT_S))
        return

    if t == ActionType.RESTART:
        # Runner normally rewrites RESTART -> GOTO(start_url) and sets action.url.
        if action.url:
            await page.goto(action.url)
        else:
            await page.reload()
        return

    if t == ActionType.ANSWER:
        # No-op: the run loop treats ANSWER as "task complete".
        return

    # Unknown action type: do nothing rather than crash the session.
    return
