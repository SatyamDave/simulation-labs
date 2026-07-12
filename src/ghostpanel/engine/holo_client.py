"""Holo Models API client (Agent 1).

* ``LiveHoloClient`` — the real thing. Holo is OpenAI-compatible, so we use
  ``AsyncOpenAI`` with a swapped ``base_url`` and send screenshots as base64
  data URIs. A shared asyncio token bucket keeps the whole swarm inside one
  RPM budget (free tier = 10 RPM); 429s are retried with backoff.

* ``FakeHoloClient`` — deterministic, network-free stand-in used by every
  agent's tests. Its behaviour is a stable cross-agent contract; see its
  docstring before changing anything.

smart_resize / coordinate policy
--------------------------------
We NEVER change the dimensions of the screenshot we send (perturbation.py's
golden rule), so the coordinates Holo returns are already in the true pixel
space of the image — no remap needed. As a safety net for the documented
legacy behaviour (normalized 0-1000 coords), ``_maybe_rescale`` detects
coordinates that lie outside the image but inside [0, 1000] and rescales them;
in-range coordinates are passed through untouched and finally clamped
in-bounds.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import re
import struct
import time
from typing import Optional

import openai
from openai import AsyncOpenAI

from ghostpanel_contracts import Action, ActionType, ScrollDirection

from .prompts import NAVIGATION_SYSTEM_PROMPT, localization_prompt, navigation_prompt

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DEFAULT_SIZE = (1280, 800)  # PersonaConfig's default viewport
_MAX_RETRIES = 5
_MAX_COMPLETION_TOKENS = 4096  # length-retry ceiling for the reasoning model


def png_size(png_bytes: bytes) -> Optional[tuple[int, int]]:
    """(width, height) from a PNG header via stdlib only; None if not a PNG."""
    if len(png_bytes) < 24 or not png_bytes.startswith(_PNG_SIGNATURE):
        return None
    w, h = struct.unpack(">II", png_bytes[16:24])
    return int(w), int(h)


class AsyncTokenBucket:
    """A simple asyncio token bucket: ``rpm`` requests per minute, shared by
    every coroutine that awaits :meth:`acquire` on the same instance."""

    def __init__(self, rpm: float) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be > 0")
        self.rate = rpm / 60.0
        self.capacity = max(1.0, float(rpm))
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self.rate
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# Response parsing (module-level so it is unit-testable without a network)
# ---------------------------------------------------------------------------
_CLICK_RE = re.compile(r"[Cc]lick\s*\(\s*(?:x\s*=\s*)?(\d+(?:\.\d+)?)\s*,\s*(?:y\s*=\s*)?(\d+(?:\.\d+)?)\s*\)")
_URL_RE = re.compile(r"https?://\S+")
_WAIT_RE = re.compile(r"\bwait\b(?:\s*\(?\s*(\d+(?:\.\d+)?))?", re.IGNORECASE)
_SCROLL_RE = re.compile(r"\bscroll\b.*?\b(up|down|left|right)\b", re.IGNORECASE | re.DOTALL)
_ANSWER_RE = re.compile(r"\banswer\b\s*[:(]?\s*[\"']?(.+?)[\"']?\s*\)?\s*$", re.IGNORECASE | re.DOTALL)

_ACTION_NAME_MAP = {
    "click": ActionType.CLICK,
    "click_element": ActionType.CLICK,
    "write": ActionType.WRITE,
    "write_element": ActionType.WRITE,
    "write_element_abs": ActionType.WRITE,
    "type": ActionType.WRITE,
    "scroll": ActionType.SCROLL,
    "go_back": ActionType.GO_BACK,
    "back": ActionType.GO_BACK,
    "refresh": ActionType.REFRESH,
    "reload": ActionType.REFRESH,
    "wait": ActionType.WAIT,
    "goto": ActionType.GOTO,
    "go_to": ActionType.GOTO,
    "restart": ActionType.RESTART,
    "answer": ActionType.ANSWER,
    "final_answer": ActionType.ANSWER,
}


def _extract_json(raw: str) -> Optional[dict]:
    """First balanced ``{...}`` block in ``raw`` that parses as a JSON object."""
    for start, ch in enumerate(raw):
        if ch != "{":
            continue
        depth = 0
        for end in range(start, len(raw)):
            if raw[end] == "{":
                depth += 1
            elif raw[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(raw[start : end + 1])
                    except json.JSONDecodeError:
                        break  # try the next opening brace
                    if isinstance(obj, dict):
                        return obj
                    break
    return None


def _caption_for(
    action_type: ActionType,
    *,
    element: str = "",
    x: Optional[int] = None,
    y: Optional[int] = None,
    text: Optional[str] = None,
    direction: Optional[ScrollDirection] = None,
    url: Optional[str] = None,
    seconds: Optional[float] = None,
) -> str:
    if action_type is ActionType.CLICK:
        return f"Clicking {element}" if element else f"Clicking at ({x}, {y})"
    if action_type is ActionType.WRITE:
        target = f" into {element}" if element else ""
        return f"Typing '{(text or '')[:40]}'{target}"
    if action_type is ActionType.SCROLL:
        return f"Scrolling {direction.value if direction else 'down'}"
    if action_type is ActionType.GO_BACK:
        return "Going back"
    if action_type is ActionType.REFRESH:
        return "Refreshing the page"
    if action_type is ActionType.WAIT:
        return f"Waiting {seconds:g}s" if seconds else "Waiting"
    if action_type is ActionType.GOTO:
        return f"Going to {url}"
    if action_type is ActionType.RESTART:
        return "Restarting the task"
    if action_type is ActionType.ANSWER:
        return f"Finished: {(text or '')[:60]}" if text else "Finished"
    return action_type.value


def _maybe_rescale(
    x: Optional[int], y: Optional[int], image_size: Optional[tuple[int, int]]
) -> tuple[Optional[int], Optional[int]]:
    """Map Holo coordinates into true image pixels and clamp in-bounds.

    Live probe (2026-07-12, holo3-1-35b-a3b, 1280x800 screenshot, ground truth
    from Playwright bounding_box): the model returns 0-1000 NORMALIZED
    coordinates — raw (426,536) vs button center (547,430); scaled by
    (w/1000, h/1000) it lands within 2px. So any coordinate pair inside
    [0, 1000]^2 is treated as normalized; genuine pixel coords beyond 1000
    (large viewports) pass through untouched.
    """
    if x is None or y is None or image_size is None:
        return x, y
    w, h = image_size
    if 0 <= x <= 1000 and 0 <= y <= 1000:
        x = round(x * w / 1000)
        y = round(y * h / 1000)
    return min(max(x, 0), w - 1), min(max(y, 0), h - 1)


def parse_navigation_response(raw: str, image_size: Optional[tuple[int, int]] = None) -> Action:
    """Parse a Holo navigation reply into a contract :class:`Action`.

    Primary path: the strict single-JSON-object format our prompt requests
    (also tolerates the cookbook's nested ``{"action": {...}}`` NavigationStep
    shape). Fallback path: lenient regexes over free text (``Click(x, y)``,
    ``scroll down``, a bare URL after "goto", ...). If nothing parses, a 1 s
    WAIT is returned so a session degrades instead of crashing.
    """
    data = _extract_json(raw)
    if data is not None:
        inner = data.get("action")
        if isinstance(inner, dict):  # cookbook NavigationStep: {"action": {"action"/"name": ...}}
            name = inner.get("action") or inner.get("name") or ""
            fields = {**inner, **(inner.get("arguments") or {})}
        else:
            name = inner or data.get("name") or ""
            fields = data
        action_type = _ACTION_NAME_MAP.get(str(name).strip().lower())
        if action_type is not None:
            return _action_from_fields(action_type, fields, raw, image_size)

    return _parse_freeform(raw, image_size)


def _action_from_fields(
    action_type: ActionType, fields: dict, raw: str, image_size: Optional[tuple[int, int]]
) -> Action:
    def _num(*keys: str) -> Optional[float]:
        for k in keys:
            v = fields.get(k)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v)
                except ValueError:
                    pass
        return None

    def _str(*keys: str) -> Optional[str]:
        for k in keys:
            v = fields.get(k)
            if isinstance(v, str) and v:
                return v
        return None

    xf, yf = _num("x"), _num("y")
    x = round(xf) if xf is not None else None
    y = round(yf) if yf is not None else None
    x, y = _maybe_rescale(x, y, image_size)
    text = _str("text", "content", "value", "answer")
    element = _str("element", "element_description", "description") or ""
    url = _str("url")
    seconds = _num("seconds", "duration", "time")
    direction: Optional[ScrollDirection] = None
    d = _str("direction")
    if d:
        try:
            direction = ScrollDirection(d.strip().lower())
        except ValueError:
            direction = ScrollDirection.DOWN

    if action_type is ActionType.SCROLL and direction is None:
        direction = ScrollDirection.DOWN
    if action_type is ActionType.WAIT and seconds is None:
        seconds = 1.0

    return Action(
        type=action_type,
        x=x if action_type in (ActionType.CLICK, ActionType.WRITE) else None,
        y=y if action_type in (ActionType.CLICK, ActionType.WRITE) else None,
        text=text if action_type in (ActionType.WRITE, ActionType.ANSWER) else None,
        direction=direction if action_type is ActionType.SCROLL else None,
        url=url if action_type is ActionType.GOTO else None,
        seconds=seconds if action_type is ActionType.WAIT else None,
        caption=_caption_for(
            action_type, element=element, x=x, y=y, text=text,
            direction=direction, url=url, seconds=seconds,
        ),
        raw=raw,
    )


def _parse_freeform(raw: str, image_size: Optional[tuple[int, int]]) -> Action:
    lowered = raw.lower()

    m = _CLICK_RE.search(raw)
    if m:
        x, y = _maybe_rescale(round(float(m.group(1))), round(float(m.group(2))), image_size)
        return Action(type=ActionType.CLICK, x=x, y=y,
                      caption=_caption_for(ActionType.CLICK, x=x, y=y), raw=raw)

    m = _SCROLL_RE.search(raw)
    if m:
        direction = ScrollDirection(m.group(1).lower())
        return Action(type=ActionType.SCROLL, direction=direction,
                      caption=_caption_for(ActionType.SCROLL, direction=direction), raw=raw)

    if "go_back" in lowered or "go back" in lowered:
        return Action(type=ActionType.GO_BACK, caption=_caption_for(ActionType.GO_BACK), raw=raw)
    if "restart" in lowered:
        return Action(type=ActionType.RESTART, caption=_caption_for(ActionType.RESTART), raw=raw)
    if "refresh" in lowered or "reload" in lowered:
        return Action(type=ActionType.REFRESH, caption=_caption_for(ActionType.REFRESH), raw=raw)

    if "goto" in lowered or "go to" in lowered:
        m = _URL_RE.search(raw)
        if m:
            url = m.group(0).rstrip('.,)"\'')
            return Action(type=ActionType.GOTO, url=url,
                          caption=_caption_for(ActionType.GOTO, url=url), raw=raw)

    m = _ANSWER_RE.search(raw)
    if m:
        text = m.group(1).strip()
        return Action(type=ActionType.ANSWER, text=text,
                      caption=_caption_for(ActionType.ANSWER, text=text), raw=raw)

    m = _WAIT_RE.search(raw)
    if m:
        seconds = float(m.group(1)) if m.group(1) else 1.0
        return Action(type=ActionType.WAIT, seconds=seconds,
                      caption=_caption_for(ActionType.WAIT, seconds=seconds), raw=raw)

    return Action(type=ActionType.WAIT, seconds=1.0,
                  caption="Could not parse model output; waiting", raw=raw)


def parse_click_response(raw: str, image_size: Optional[tuple[int, int]] = None) -> tuple[int, int]:
    """Parse a localizer reply: ``Click(x, y)`` text or a JSON click object."""
    m = _CLICK_RE.search(raw)
    if m:
        x, y = round(float(m.group(1))), round(float(m.group(2)))
    else:
        data = _extract_json(raw)
        if data is None:
            raise ValueError(f"No Click(x, y) found in localizer response: {raw!r}")
        inner = data.get("action") if isinstance(data.get("action"), dict) else data
        try:
            x, y = round(float(inner["x"])), round(float(inner["y"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"No Click(x, y) found in localizer response: {raw!r}") from exc
    x, y = _maybe_rescale(x, y, image_size)
    return int(x), int(y)


def _image_part(png_bytes: bytes) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


# ---------------------------------------------------------------------------
# Live client
# ---------------------------------------------------------------------------
class LiveHoloClient:
    """Real Holo Models API client (OpenAI-compatible, base_url swap).

    A single :class:`AsyncTokenBucket` should be shared by the whole swarm:
    either pass the same ``limiter`` instance to every client, or build all
    clients via :meth:`LiveHoloClient.shared` (process-wide limiter from env).
    """

    _shared_limiter: Optional[AsyncTokenBucket] = None

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        rpm: float = 10,
        limiter: Optional[AsyncTokenBucket] = None,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.limiter = limiter if limiter is not None else AsyncTokenBucket(rpm)

    @classmethod
    def shared(
        cls,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        rpm: Optional[float] = None,
    ) -> "LiveHoloClient":
        """A client wired to one process-wide rate limiter; args default to
        HAI_API_KEY / HAI_BASE_URL / HAI_MODEL / HAI_RPM from the env."""
        rpm = rpm if rpm is not None else float(os.getenv("HAI_RPM", "10"))
        if cls._shared_limiter is None:
            cls._shared_limiter = AsyncTokenBucket(rpm)
        return cls(
            api_key=api_key or os.getenv("HAI_API_KEY", ""),
            base_url=base_url or os.getenv("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
            model=model or os.getenv("HAI_MODEL", "holo3-1-35b-a3b"),
            rpm=rpm,
            limiter=cls._shared_limiter,
        )

    async def _complete(self, messages: list[dict], max_tokens: int = 2048) -> str:
        # Holo 3.1 is a REASONING model: it streams chain-of-thought into a
        # non-standard `reasoning` field and only then emits `content`. A small
        # max_tokens gets fully consumed by reasoning (finish_reason="length",
        # content=None) — so budgets must be generous, one length-retry doubles
        # the budget, and the reasoning text is the last-resort answer source.
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            await self.limiter.acquire()
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
                choice = resp.choices[0]
                content = choice.message.content or ""
                if content.strip():
                    return content
                if choice.finish_reason == "length" and max_tokens < _MAX_COMPLETION_TOKENS:
                    max_tokens = _MAX_COMPLETION_TOKENS
                    continue
                reasoning = getattr(choice.message, "reasoning", None) or ""
                return reasoning
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as exc:
                last_exc = exc
                await asyncio.sleep(min(30.0, 1.5 * 2**attempt) + random.uniform(0, 0.5))
        raise RuntimeError(f"Holo request failed after {_MAX_RETRIES} attempts") from last_exc

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        """Return (x, y) in the pixel space of the image passed in."""
        raw = await self._complete(
            [{
                "role": "user",
                "content": [_image_part(image_png),
                            {"type": "text", "text": localization_prompt(instruction)}],
            }],
            max_tokens=1024,
        )
        return parse_click_response(raw, png_size(image_png))

    async def navigate(self, image_png: bytes, task: str, history: list[str]) -> Action:
        """Return the next Action given a screenshot, the task, and past-action
        captions. ``history`` must NOT include the "TASK: ..." seed entry."""
        raw = await self._complete(
            [
                {"role": "system", "content": NAVIGATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [_image_part(image_png),
                                {"type": "text", "text": navigation_prompt(task, history)}],
                },
            ]
        )
        return parse_navigation_response(raw, png_size(image_png))


# ---------------------------------------------------------------------------
# Fake client (cross-agent test dependency — keep behaviour stable!)
# ---------------------------------------------------------------------------
class FakeHoloClient:
    """Deterministic, dependency-free HoloClient for tests. NO network, NO
    third-party imports (contracts + stdlib only). Agents 2/3/5 import this —
    its behaviour is a frozen convention:

    * ``navigate()`` returns ``scripted_actions`` in FIFO order. Once the
      script is exhausted (or if none was given) every call returns the
      default action: a CLICK at the **centre of the screenshot** — dims read
      from the PNG header, falling back to (1280, 800) when the bytes are not
      a PNG — with ``caption="Clicking the centre of the page"`` and
      ``raw="FakeHoloClient: Click(<x>, <y>)"``.
    * ``localize()`` returns the centre of the image, same fallback.
    * Every call is appended to ``self.calls`` as a dict with keys
      ``method`` ("navigate"/"localize"), ``task`` or ``instruction``, and
      ``history`` — handy for asserting what the agent sent.
    """

    def __init__(self, scripted_actions: Optional[list[Action]] = None) -> None:
        self._script: list[Action] = list(scripted_actions or [])
        self.calls: list[dict] = []

    @staticmethod
    def _center(image_png: bytes) -> tuple[int, int]:
        w, h = png_size(image_png) or _DEFAULT_SIZE
        return w // 2, h // 2

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        self.calls.append({"method": "localize", "instruction": instruction})
        return self._center(image_png)

    async def navigate(self, image_png: bytes, task: str, history: list[str]) -> Action:
        self.calls.append({"method": "navigate", "task": task, "history": list(history)})
        if self._script:
            return self._script.pop(0)
        x, y = self._center(image_png)
        return Action(
            type=ActionType.CLICK,
            x=x,
            y=y,
            caption="Clicking the centre of the page",
            raw=f"FakeHoloClient: Click({x}, {y})",
        )
