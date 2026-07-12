"""Map contract Actions onto Playwright page calls.

Golden rule (see CLAUDE.md): ``Action.x`` / ``Action.y`` arrive already in TRUE
viewport CSS pixels — the engine has applied tremor jitter and any smart_resize
remap. We execute them verbatim and NEVER rescale.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Page

from ghostpanel_contracts import Action, ActionType, ScrollDirection

#: CSS pixels one SCROLL action moves the page by.
SCROLL_PX = 400

#: Hard cap on a WAIT action, in seconds.
WAIT_CAP_S = 10.0

_SCROLL_DELTAS: dict[ScrollDirection, tuple[int, int]] = {
    ScrollDirection.UP: (0, -SCROLL_PX),
    ScrollDirection.DOWN: (0, SCROLL_PX),
    ScrollDirection.LEFT: (-SCROLL_PX, 0),
    ScrollDirection.RIGHT: (SCROLL_PX, 0),
}


async def execute_action(page: Page, action: Action, target_url: str = "") -> None:
    """Execute one decoded ``Action`` on the live page.

    ``target_url`` is the session's start URL. It is only consulted for
    ``RESTART`` (Holo's RestartAction = "go back to the beginning of the
    task"); the session runner always passes it.
    """
    if action.type is ActionType.CLICK:
        if action.x is None or action.y is None:
            raise ValueError(f"CLICK action missing coordinates: {action!r}")
        await page.mouse.click(action.x, action.y)

    elif action.type is ActionType.WRITE:
        # Matches Holo's WriteElementAction semantics: focus the target,
        # type the text, then press Enter.
        if action.x is not None and action.y is not None:
            await page.mouse.click(action.x, action.y)
        await page.keyboard.type(action.text or "")
        await page.keyboard.press("Enter")

    elif action.type is ActionType.SCROLL:
        dx, dy = _SCROLL_DELTAS[action.direction or ScrollDirection.DOWN]
        await page.mouse.wheel(dx, dy)

    elif action.type is ActionType.GO_BACK:
        await page.go_back()

    elif action.type is ActionType.REFRESH:
        await page.reload()

    elif action.type is ActionType.GOTO:
        if not action.url:
            raise ValueError(f"GOTO action missing url: {action!r}")
        await page.goto(action.url)

    elif action.type is ActionType.WAIT:
        await asyncio.sleep(min(max(action.seconds or 2.0, 0.0), WAIT_CAP_S))

    elif action.type is ActionType.RESTART:
        if not target_url:
            raise ValueError("RESTART needs the session's start url (target_url)")
        await page.goto(target_url)

    elif action.type is ActionType.ANSWER:
        # No browser effect; the session loop treats ANSWER as "persona
        # declares the task done".
        pass
