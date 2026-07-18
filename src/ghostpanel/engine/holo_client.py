"""Holo Models API clients.

``LiveHoloClient`` wraps the OpenAI-compatible Holo endpoint. ``FakeHoloClient``
is a dependency-free, deterministic stand-in that every other module (runner,
server, tests) imports so the swarm runs with no network.

Coordinate contract: ``localize`` / ``navigate`` return coordinates in the TRUE
pixel space of the image passed in. IMPORTANT: the hosted Holo3.1 API returns
coordinates normalized to a 0-1000 grid (confirmed empirically — a click on a
button whose true centre was (547,430) in a 1280x800 screenshot came back as
Click(426,536), i.e. 426/1000*1280=545, 536/1000*800=429). So the LIVE client
ALWAYS denormalizes model coords via ``_denormalize`` (0-1000 -> pixels). The
``FakeHoloClient`` returns pixel coords directly and does NOT denormalize.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from typing import Any, Optional

from ghostpanel_contracts import Action, ActionType, ScrollDirection

from . import prompts

# ---------------------------------------------------------------------------
# Shared asyncio token-bucket rate limiter
# ---------------------------------------------------------------------------
class RateLimiter:
    """A simple asyncio token bucket sized by requests-per-minute.

    ONE instance is meant to be shared across every persona's client so the whole
    swarm respects a single budget. Refills continuously at ``rpm / 60`` tokens
    per second. Burst capacity is deliberately TINY (<= 2 tokens): the hosted
    Holo API enforces even ~rpm/60 pacing with no burst allowance (verified
    live: a burst of 5 on a 5 RPM key got 429 + retry-after=11s), so bursting
    just triggers a 429/backoff storm that is slower than even pacing.
    """

    def __init__(self, rpm: float = 10.0) -> None:
        self.rpm = float(rpm) if rpm and rpm > 0 else 10.0
        self._capacity = min(2.0, max(1.0, self.rpm))
        self._tokens = self._capacity
        self._rate = self.rpm / 60.0  # tokens per second
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._updated = now

    async def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait_s = deficit / self._rate if self._rate > 0 else 1.0
            await asyncio.sleep(min(max(wait_s, 0.01), 60.0))


# ---------------------------------------------------------------------------
# Parsing helpers (shared by Live client; robust to several output shapes)
# ---------------------------------------------------------------------------
_CLICK_RE = re.compile(r"click\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)", re.I)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
# Holo 3.1 frequently emits {"action": "click", "x": 426, 536} — a bare number
# where the "y" key should be (verified live). These repair the two observed
# key-dropped shapes so the JSON parse succeeds instead of falling back.
_MISSING_Y_RE = re.compile(r'("x"\s*:\s*-?\d+(?:\.\d+)?\s*,\s*)(-?\d+(?:\.\d+)?)(?=\s*[,}])')
_MISSING_X_RE = re.compile(r'([{,]\s*)(-?\d+(?:\.\d+)?)(\s*,\s*"y"\s*:)')


def _repair_json(fragment: str) -> str:
    """Best-effort repair of Holo's key-dropped coordinate JSON."""
    fragment = _MISSING_Y_RE.sub(lambda m: f'{m.group(1)}"y": {m.group(2)}', fragment)
    fragment = _MISSING_X_RE.sub(lambda m: f'{m.group(1)}"x": {m.group(2)}{m.group(3)}', fragment)
    return fragment

_ACTION_ALIASES = {
    "click": ActionType.CLICK,
    "left_click": ActionType.CLICK,
    "tap": ActionType.CLICK,
    "write": ActionType.WRITE,
    "type": ActionType.WRITE,
    "input": ActionType.WRITE,
    "fill": ActionType.WRITE,
    "scroll": ActionType.SCROLL,
    "go_back": ActionType.GO_BACK,
    "goback": ActionType.GO_BACK,
    "back": ActionType.GO_BACK,
    "refresh": ActionType.REFRESH,
    "reload": ActionType.REFRESH,
    "wait": ActionType.WAIT,
    "goto": ActionType.GOTO,
    "navigate": ActionType.GOTO,
    "restart": ActionType.RESTART,
    "answer": ActionType.ANSWER,
    "done": ActionType.ANSWER,
    "finish": ActionType.ANSWER,
}


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _clamp(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    return min(max(x, 0), max(w - 1, 0)), min(max(y, 0), max(h - 1, 0))


def _denormalize(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    """Map Holo's 0-1000 normalized coords to true pixels in the image space,
    then clamp. Used ONLY for real model output (see module docstring)."""
    return _clamp(int(round(x / 1000.0 * w)), int(round(y / 1000.0 * h)), w, h)


def _caption_for(action_type: ActionType, x=None, y=None, text=None,
                 direction=None, url=None, seconds=None, label=None) -> str:
    if action_type == ActionType.CLICK:
        return f"Clicking {label}" if label else f"Clicking at ({x}, {y})"
    if action_type == ActionType.WRITE:
        snippet = (text or "")[:30]
        return f"Typing '{snippet}' into {label}" if label else f"Typing '{snippet}'"
    if action_type == ActionType.SCROLL:
        return f"Scrolling {direction.value if direction else 'down'}"
    if action_type == ActionType.GO_BACK:
        return "Going back"
    if action_type == ActionType.REFRESH:
        return "Refreshing the page"
    if action_type == ActionType.WAIT:
        return f"Waiting {seconds or 1}s"
    if action_type == ActionType.GOTO:
        return f"Navigating to {url}"
    if action_type == ActionType.RESTART:
        return "Restarting the task"
    if action_type == ActionType.ANSWER:
        return f"Done: {(text or '').strip()[:40]}"
    return str(action_type.value)


def parse_click(text: str) -> Optional[tuple[int, int]]:
    """Parse a ``Click(x, y)`` short form from model text."""
    m = _CLICK_RE.search(text or "")
    if not m:
        return None
    return int(round(float(m.group(1)))), int(round(float(m.group(2))))


def parse_action(text: str, w: int, h: int, normalize: bool = False) -> Action:
    """Parse model output into an Action. Tries JSON first, then Click(x,y),
    then a scroll/keyword fallback; defaults to a center click if all fail.

    ``normalize=True`` denormalizes model-provided coords from Holo's 0-1000 grid
    to pixels (use for LIVE Holo output). Fallback/center coords are always in
    pixel space and are never denormalized. The FakeHoloClient uses the default
    ``normalize=False`` so its scripted pixel coords pass through unchanged.
    """
    raw = text or ""

    # 1. Try a JSON object anywhere in the text (repairing Holo's known
    #    key-dropped coordinate shape if the first parse fails).
    obj = None
    m = _JSON_OBJ_RE.search(raw)
    if m:
        for candidate in (m.group(0), _repair_json(m.group(0))):
            try:
                obj = json.loads(candidate)
                break
            except (json.JSONDecodeError, ValueError):
                obj = None
    if isinstance(obj, dict):
        parsed = _action_from_dict(obj, w, h, raw, normalize=normalize)
        if parsed is not None:
            return parsed

    # 1b. Malformed-JSON click salvage. The live model sometimes drops the "y"
    # key — observed verbatim: {"action": "click", "x": 426, 536} — which fails
    # json.loads and has no Click(x, y) form. If the blob names a click-like
    # action, take its first two numbers as the (x, y) pair.
    if obj is None and m is not None:
        blob = m.group(0)
        if re.search(r'"action"\s*:\s*"(?:left_)?(?:click|tap)"', blob, re.I):
            nums = re.findall(r"-?\d+(?:\.\d+)?", blob)
            if len(nums) >= 2:
                x, y = (_denormalize if normalize else _clamp)(
                    int(round(float(nums[0]))), int(round(float(nums[1]))), w, h
                )
                return Action(type=ActionType.CLICK, x=x, y=y,
                              caption=_caption_for(ActionType.CLICK, x=x, y=y), raw=raw)

    # 2. Try Click(x, y) short form.
    click = parse_click(raw)
    if click is not None:
        x, y = (_denormalize if normalize else _clamp)(click[0], click[1], w, h)
        return Action(type=ActionType.CLICK, x=x, y=y,
                      caption=_caption_for(ActionType.CLICK, x=x, y=y), raw=raw)

    # 3. Keyword fallbacks.
    low = raw.lower()
    for direction in ScrollDirection:
        if f"scroll {direction.value}" in low or f"scroll_{direction.value}" in low:
            return Action(type=ActionType.SCROLL, direction=direction,
                          caption=_caption_for(ActionType.SCROLL, direction=direction),
                          raw=raw)
    if "go_back" in low or "go back" in low:
        return Action(type=ActionType.GO_BACK,
                      caption=_caption_for(ActionType.GO_BACK), raw=raw)
    if "refresh" in low or "reload" in low:
        return Action(type=ActionType.REFRESH,
                      caption=_caption_for(ActionType.REFRESH), raw=raw)

    # 4. A click intent with two loose numbers somewhere in the text — take the
    #    last coordinate pair rather than inventing a center click.
    if "click" in low:
        nums = _NUMBER_RE.findall(raw)
        if len(nums) >= 2:
            px, py = int(round(float(nums[-2]))), int(round(float(nums[-1])))
            x, y = (_denormalize if normalize else _clamp)(px, py, w, h)
            return Action(type=ActionType.CLICK, x=x, y=y,
                          caption=_caption_for(ActionType.CLICK, x=x, y=y), raw=raw)

    # 5. Give up: click the center so the runner still makes progress.
    cx, cy = w // 2, h // 2
    return Action(type=ActionType.CLICK, x=cx, y=cy,
                  caption=_caption_for(ActionType.CLICK, x=cx, y=cy),
                  raw=raw, text="unparsed")


def _action_from_dict(obj: dict, w: int, h: int, raw: str,
                      normalize: bool = False) -> Optional[Action]:
    name = obj.get("action") or obj.get("type") or obj.get("name")
    if not name:
        return None
    action_type = _ACTION_ALIASES.get(str(name).strip().lower())
    if action_type is None:
        return None

    x = _to_int(obj.get("x"))
    y = _to_int(obj.get("y"))
    # some shapes nest coords: {"coordinate": [x, y]} or {"position": {...}}
    if (x is None or y is None):
        coord = obj.get("coordinate") or obj.get("coordinates") or obj.get("position")
        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
            x = _to_int(coord[0]) if x is None else x
            y = _to_int(coord[1]) if y is None else y
        elif isinstance(coord, dict):
            x = _to_int(coord.get("x")) if x is None else x
            y = _to_int(coord.get("y")) if y is None else y

    text = obj.get("text") or obj.get("value") or obj.get("content")
    url = obj.get("url") or obj.get("href")
    seconds = obj.get("seconds")
    if seconds is None:
        seconds = obj.get("duration") or obj.get("time")
    try:
        seconds = float(seconds) if seconds is not None else None
    except (TypeError, ValueError):
        seconds = None

    direction = None
    d = obj.get("direction")
    if d:
        try:
            direction = ScrollDirection(str(d).strip().lower())
        except ValueError:
            direction = ScrollDirection.DOWN

    if x is not None and y is not None:
        x, y = (_denormalize if normalize else _clamp)(x, y, w, h)

    if action_type in (ActionType.CLICK, ActionType.WRITE) and (x is None or y is None):
        # coords required but missing -> center them (pixel space; not denormalized)
        x, y = w // 2, h // 2
    if action_type == ActionType.SCROLL and direction is None:
        direction = ScrollDirection.DOWN

    label = obj.get("label") or obj.get("element") or obj.get("target")
    label = str(label).strip()[:60] if label else None
    caption = _caption_for(action_type, x=x, y=y, text=text,
                           direction=direction, url=url, seconds=seconds,
                           label=label)
    return Action(
        type=action_type,
        x=x if action_type in (ActionType.CLICK, ActionType.WRITE) else None,
        y=y if action_type in (ActionType.CLICK, ActionType.WRITE) else None,
        text=str(text) if text is not None else None,
        direction=direction,
        url=str(url) if url is not None else None,
        seconds=seconds if action_type == ActionType.WAIT else None,
        caption=caption,
        raw=raw,
    )


def _data_uri(image_png: bytes) -> str:
    b64 = base64.b64encode(image_png).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _png_size(image_png: bytes) -> tuple[int, int]:
    """Read PNG dimensions from the IHDR chunk without importing Pillow."""
    if len(image_png) >= 24 and image_png[:8] == b"\x89PNG\r\n\x1a\n":
        w = int.from_bytes(image_png[16:20], "big")
        h = int.from_bytes(image_png[20:24], "big")
        if w > 0 and h > 0:
            return w, h
    # fallback via Pillow if it's not a plain PNG
    import io
    from PIL import Image
    with Image.open(io.BytesIO(image_png)) as im:
        return im.size


# ---------------------------------------------------------------------------
# Live client
# ---------------------------------------------------------------------------
class LiveHoloClient:
    """Real Holo Models client (OpenAI-compatible). Satisfies HoloClient."""

    # This client returns coords expressed relative to the IMAGE it was sent
    # (0-1000 grid over the sent frame), so the agent may downscale the frame for
    # transport and must scale the returned coords back up. Backends that return
    # TRUE viewport pixels (Fake/Echo) leave this False so the agent sends the
    # frame at full size and executes their coords verbatim — no double-scaling.
    coords_relative_to_sent_image = True

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        rpm: float = 10.0,
        limiter: Optional[RateLimiter] = None,
        max_retries: int = 4,
        max_concurrency: Optional[int] = None,
    ) -> None:
        from openai import AsyncOpenAI

        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.rpm = rpm
        self.max_retries = max_retries
        # Share ONE limiter across personas by passing the same instance.
        self.limiter = limiter if limiter is not None else RateLimiter(rpm)
        # Cap simultaneously in-flight requests. The RateLimiter bounds the RATE,
        # but N personas can still each hold an open connection during a multi-
        # second vision call; some endpoints (e.g. a free-tier quota) drop those
        # concurrent connections. This semaphore bounds concurrency across the
        # whole swarm since one client instance is shared by every persona.
        # None => effectively unbounded (large cap).
        self._sem = asyncio.Semaphore(max_concurrency if max_concurrency and max_concurrency > 0 else 1000)
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    @classmethod
    def shared(
        cls,
        api_key: str,
        base_url: str,
        model: str,
        rpm: float = 10.0,
    ) -> tuple["LiveHoloClient", RateLimiter]:
        """Convenience: build a client and return (client, limiter) so callers can
        thread the SAME limiter into every subsequent persona's client."""
        limiter = RateLimiter(rpm)
        return cls(api_key, base_url, model, rpm, limiter=limiter), limiter

    async def _chat(self, image_png: bytes, prompt: str) -> str:
        data_uri = _data_uri(image_png)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ]
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            await self.limiter.acquire()
            try:
                async with self._sem:  # bound concurrent in-flight requests
                    resp = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0.0,
                    )
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 - inspect for 429/rate limits
                last_err = exc
                status = getattr(exc, "status_code", None)
                name = type(exc).__name__.lower()
                is_rate = status == 429 or "ratelimit" in name or "429" in str(exc)
                if is_rate and attempt < self.max_retries - 1:
                    await asyncio.sleep(min(2.0 ** attempt, 30.0))
                    continue
                if attempt < self.max_retries - 1 and (
                    "timeout" in name or "connection" in name or "apiconnection" in name
                ):
                    await asyncio.sleep(min(2.0 ** attempt, 10.0))
                    continue
                raise
        assert last_err is not None
        raise last_err

    def _localize_prompt(self, instruction: str) -> str:
        """Prompt used by ``localize``. Subclass hook (see GeminiClient)."""
        return prompts.localization_prompt(instruction)

    def _navigation_prompt(self, task: str, history: list[str]) -> str:
        """Prompt used by ``navigate``. Subclass hook (see GeminiClient)."""
        return _navigate_prompt(task, history)

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        w, h = _png_size(image_png)
        prompt = self._localize_prompt(instruction)
        text = await self._chat(image_png, prompt)
        click = parse_click(text)
        if click is None:
            # last-ditch: any "x, y" pair (normalized), else pixel-space center
            m = re.search(r"(-?\d+)\s*,\s*(-?\d+)", text or "")
            if m:
                return _denormalize(int(m.group(1)), int(m.group(2)), w, h)
            return _clamp(w // 2, h // 2, w, h)
        # Real Holo coords are 0-1000 normalized -> map to true pixels.
        return _denormalize(int(click[0]), int(click[1]), w, h)

    async def navigate(self, image_png: bytes, task: str, history: list[str]) -> Action:
        w, h = _png_size(image_png)
        # navigation_prompt needs a persona for its literacy note; the agent
        # normally builds the full prompt. Here we accept task+history directly and
        # build a persona-free prompt using a minimal shim.
        prompt = self._navigation_prompt(task, history)
        text = await self._chat(image_png, prompt)
        # normalize=True: denormalize Holo's 0-1000 coords to true pixels.
        return parse_action(text, w, h, normalize=True)


def _navigate_prompt(task: str, history: list[str]) -> str:
    """Persona-free navigation prompt (used when navigate() is called directly on
    the HoloClient contract, which has no persona argument). The persona agent
    injects its literacy note by prepending it to the task string."""
    from ghostpanel_contracts import PersonaConfig

    return prompts.navigation_prompt(task, history, PersonaConfig(id="_", name="_"))


# ---------------------------------------------------------------------------
# Fake client — deterministic, dependency-free, network-free
# ---------------------------------------------------------------------------
class FakeHoloClient:
    """Deterministic HoloClient for tests and offline runs.

    ``scripted_actions`` may be a list of:
      * ``Action`` — returned as-is (consumed FIFO), or
      * ``(x, y)`` tuple — turned into a CLICK Action, or
      * ``dict`` — parsed via the same parser as the live client.
    When the queue is empty (or None), returns a deterministic center click.

    ``navigate`` consumes the queue; ``localize`` returns the queued/next click
    coords or the image center. No network, no external deps beyond stdlib.
    """

    def __init__(self, scripted_actions: Optional[list] = None) -> None:
        self._scripted = list(scripted_actions) if scripted_actions else []
        self._nav_calls = 0
        self._loc_calls = 0

    def _next_scripted(self, w: int, h: int) -> Action:
        if self._scripted:
            item = self._scripted.pop(0)
            return self._coerce(item, w, h)
        cx, cy = w // 2, h // 2
        return Action(
            type=ActionType.CLICK, x=cx, y=cy,
            caption=f"Clicking at ({cx}, {cy})",
            raw="fake:center-click",
        )

    @staticmethod
    def _coerce(item, w: int, h: int) -> Action:
        if isinstance(item, Action):
            return item
        if isinstance(item, dict):
            parsed = _action_from_dict(item, w, h, raw=json.dumps(item))
            if parsed is not None:
                return parsed
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = int(item[0]), int(item[1])
            return Action(type=ActionType.CLICK, x=x, y=y,
                          caption=f"Clicking at ({x}, {y})", raw="fake:coords")
        # unknown -> center click
        cx, cy = w // 2, h // 2
        return Action(type=ActionType.CLICK, x=cx, y=cy,
                      caption=f"Clicking at ({cx}, {cy})", raw="fake:fallback")

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        self._loc_calls += 1
        w, h = _png_size(image_png)
        if self._scripted:
            act = self._coerce(self._scripted[0], w, h)
            if act.x is not None and act.y is not None:
                return act.x, act.y
        return w // 2, h // 2

    async def navigate(self, image_png: bytes, task: str, history: list[str]) -> Action:
        self._nav_calls += 1
        w, h = _png_size(image_png)
        return self._next_scripted(w, h)
