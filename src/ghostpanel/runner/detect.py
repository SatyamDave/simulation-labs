"""Success / stuck / screen-change detection helpers for the session loop."""

from __future__ import annotations

import inspect
import io
import re
from typing import Awaitable, Callable, Optional, Union

# Appended by the session loop to a history caption when the following frame was
# visually identical — tells the model (and the stuck detector) the action was a dud.
NO_CHANGE_NOTE = " — nothing changed on screen"

# A success predicate takes the live page and returns (optionally awaitable) truthiness.
SuccessPredicate = Callable[[object], Union[bool, Awaitable[bool]]]

# When NO caller predicate is supplied, success is determined ONLY by the agent
# emitting an `answer()` action (handled in the session loop) — NOT by scanning page
# text. Generic markers like "welcome"/"success" false-positive constantly on real
# content sites (e.g. "Welcome to Wikipedia"), so the default heuristic matches
# nothing. Callers that know a page's success signal pass an explicit predicate.
_DEFAULT_SUCCESS_SELECTORS: tuple[str, ...] = ()


# "Clicking at (960, 312)" (engine caption) or "clicking (960, 312)" (runner default).
_CLICK_CAPTION_RE = re.compile(r"^click\w*\s*(?:at\s*)?\((-?\d+),\s*(-?\d+)\)", re.I)


def _core_caption(caption: str) -> str:
    """Caption with any runner annotation (e.g. the no-change note) stripped."""
    return caption.split(" — ", 1)[0].strip()


def is_stuck(history: list[str], window: int = 3, click_radius_px: int = 14) -> bool:
    """True when the last `window` actions form a no-progress loop.

    `history` is the list of action captions (what the UI tile shows). Two ways
    to be stuck:
      * the exact same caption `window` times in a row (same intent), or
      * `window` clicks within `click_radius_px` of each other where the later
        ones are annotated with NO_CHANGE_NOTE — i.e. hammering the same dead
        spot (tremor jitter makes the coords, and thus captions, differ slightly).
    """
    if window < 2 or len(history) < window:
        return False
    last = history[-window:]
    cores = [_core_caption(h) for h in last]
    if not cores[0]:
        return False
    if all(c == cores[0] for c in cores):
        return True

    # Near-identical clicks with no visible effect.
    points = []
    for core in cores:
        m = _CLICK_CAPTION_RE.match(core)
        if not m:
            return False
        points.append((int(m.group(1)), int(m.group(2))))
    x0, y0 = points[0]
    close = all(
        abs(x - x0) <= click_radius_px and abs(y - y0) <= click_radius_px
        for x, y in points[1:]
    )
    duds = sum(1 for h in last if NO_CHANGE_NOTE in h)
    return close and duds >= window - 1


def frames_similar(png_a: bytes, png_b: bytes, threshold: float = 1.5) -> bool:
    """True when two same-viewport screenshots are visually near-identical.

    Compares small grayscale thumbnails by mean absolute pixel difference so a
    blinking cursor or antialiasing noise doesn't count as change. Never raises;
    on any decode problem it returns False (assume the screen changed).
    """
    if not png_a or not png_b:
        return False
    if png_a == png_b:
        return True
    try:
        from PIL import Image, ImageChops, ImageStat

        a = Image.open(io.BytesIO(png_a)).convert("L")
        b = Image.open(io.BytesIO(png_b)).convert("L")
        if a.size != b.size:
            return False
        w = 96
        h = max(1, round(a.height * w / a.width))
        a = a.resize((w, h))
        b = b.resize((w, h))
        diff = ImageChops.difference(a, b)
        return ImageStat.Stat(diff).mean[0] < threshold
    except Exception:
        return False


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
