"""Success / stuck / loop detection helpers for the session runner."""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable, Optional, Union

from playwright.async_api import Page

#: Signature Agent 3 can pass to override the default success heuristic.
#: May be sync or async; receives the live Page, returns truthy on success.
SuccessPredicate = Callable[[Page], Union[bool, Awaitable[bool]]]

#: The first history entry is the task, formatted "TASK: <text>" (frozen
#: cross-agent convention); it is never an action caption.
TASK_PREFIX = "TASK: "

# Default heuristic: a visible success-ish element. Covers the bundled
# fixtures/hostile_form.html (#ok becomes visible on completed signup) plus a
# few common conventions. Runs inside the page so hidden elements don't count.
_DEFAULT_SUCCESS_JS = """
() => {
  const sels = ['#ok', '.success', '[data-success]', '[data-testid="success"]'];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (!el) continue;
    const visible = el.checkVisibility ? el.checkVisibility() : el.offsetParent !== null;
    if (visible) return true;
  }
  return false;
}
"""


def is_stuck(history: list[str], window: int = 3) -> bool:
    """True when the last ``window`` action captions are identical.

    A persona re-issuing the exact same action (same caption, which encodes
    the intent/coords) with nothing changing is looping — a human would have
    given up. The "TASK: ..." seed entry is excluded.
    """
    captions = [h for h in history if not h.startswith(TASK_PREFIX)]
    if len(captions) < window:
        return False
    tail = captions[-window:]
    # Identical empty captions carry no signal; don't punish a caption-less agent.
    return bool(tail[0]) and all(c == tail[0] for c in tail)


async def is_success(page: Page, predicate: Optional[SuccessPredicate] = None) -> bool:
    """Run ``predicate`` (sync or async) if given, else the default heuristic."""
    if predicate is not None:
        result = predicate(page)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)
    try:
        return bool(await page.evaluate(_DEFAULT_SUCCESS_JS))
    except Exception:
        # Page mid-navigation / context torn down — that is not success.
        return False
