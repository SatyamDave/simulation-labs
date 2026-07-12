"""Success / stuck detection helpers for the session loop."""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable, Optional, Union

# A success predicate takes the live page and returns (optionally awaitable) truthiness.
SuccessPredicate = Callable[[object], Union[bool, Awaitable[bool]]]

# When NO caller predicate is supplied, success is determined ONLY by the agent
# emitting an `answer()` action (handled in the session loop) — NOT by scanning page
# text. Generic markers like "welcome"/"success" false-positive constantly on real
# content sites (e.g. "Welcome to Wikipedia"), so the default heuristic matches
# nothing. Callers that know a page's success signal pass an explicit predicate.
_DEFAULT_SUCCESS_SELECTORS: tuple[str, ...] = ()


def is_stuck(history: list[str], window: int = 3) -> bool:
    """True when the last `window` actions are identical — a no-progress loop.

    `history` is the list of action captions (what the UI tile shows). If the persona
    keeps emitting the exact same caption (same click coord / same intent) `window`
    times in a row, we treat it as giving up.
    """
    if window < 2 or len(history) < window:
        return False
    last = history[-window:]
    return all(item == last[0] for item in last) and bool(last[0])


async def is_success(page, predicate: Optional[SuccessPredicate] = None) -> bool:
    """Run the caller-supplied success `predicate`, or a conservative default.

    The predicate may be sync or async and receives the live Playwright page.
    The default heuristic looks for a handful of common "you succeeded" elements;
    it is intentionally conservative so it never false-positives mid-flow.
    """
    if predicate is not None:
        try:
            result = predicate(page)
            if inspect.isawaitable(result):
                result = await result
            return bool(result)
        except Exception:
            return False

    # Default heuristic: any well-known success marker visible on the page.
    for selector in _DEFAULT_SUCCESS_SELECTORS:
        try:
            if await page.locator(selector).first.is_visible():
                return True
        except Exception:
            continue
    return False
