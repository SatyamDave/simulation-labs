"""End-to-end PlaywrightSessionRunner tests against fixtures/hostile_form.html.

Fully hermetic: a StubPersonaAgent replays scripted Actions (no engine / no network
beyond a localhost http.server serving the fixture). Headless Chromium.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.runner.testing import CollectingEventSink, StubPersonaAgent
from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaFinished,
    PersonaOutcome,
    PersonaStarted,
    ScrollDirection,
    SessionRunner,
    StepEvent,
    Viewport,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWPORT = {"width": 1280, "height": 900}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence request logging
        pass


@pytest.fixture(scope="session")
def http_base():
    handler = functools.partial(_QuietHandler, directory=str(REPO_ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def target_url(http_base):
    return f"{http_base}/fixtures/hostile_form.html"


@pytest.fixture
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


def make_persona(max_steps: int = 30, deadline_s: float = 60.0) -> PersonaConfig:
    return PersonaConfig(
        id="tester",
        name="Tester",
        viewport=Viewport(width=VIEWPORT["width"], height=VIEWPORT["height"]),
        max_steps=max_steps,
        deadline_s=deadline_s,
    )


def _center(box) -> tuple[int, int]:
    return (int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))


async def _measure(browser, url) -> dict:
    """Open a scratch context and read the true viewport-pixel centers of the
    elements the scripts need — mirroring the exact click/scroll the run will do."""
    ctx = await browser.new_context(viewport=VIEWPORT)
    p = await ctx.new_page()
    await p.goto(url)
    # Mirror the RUN's exact action sequence while measuring, so every
    # coordinate is read from the same page state the run will click it in
    # (the page's reveal-on-scroll layout shifts with interaction order).
    accept = _center(await p.locator("#cookie button").bounding_box())
    await p.mouse.click(*accept)
    email = _center(await p.locator("#email").bounding_box())
    await p.mouse.click(*email)                    # WRITE = click + type + Enter
    await p.keyboard.type("me@work.com")
    await p.keyboard.press("Enter")
    await p.mouse.wheel(0, 600)                    # SCROLL action
    await p.wait_for_timeout(400)                  # WAIT action
    promo = _center(await p.locator("#promo").bounding_box())
    submit = _center(await p.locator("button.btn-real").bounding_box())
    decoy = _center(await p.locator(".actions .btn-decoy").bounding_box())
    await ctx.close()
    return {"accept": accept, "email": email, "promo": promo,
            "submit": submit, "decoy": decoy}


async def _ok_visible(page) -> bool:
    return await page.locator("#ok").is_visible()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_isinstance_session_runner(browser, tmp_path):
    runner = PlaywrightSessionRunner(browser, tmp_path)
    assert isinstance(runner, SessionRunner)


async def test_decoy_then_quit_produces_video_and_events(browser, tmp_path, target_url):
    c = await _measure(browser, target_url)
    persona = make_persona()
    script = [
        Action(type=ActionType.CLICK, x=c["accept"][0], y=c["accept"][1], caption="accept cookies"),
        Action(type=ActionType.SCROLL, direction=ScrollDirection.DOWN, caption="scroll down"),
        Action(type=ActionType.CLICK, x=c["decoy"][0], y=c["decoy"][1], caption="click Explore plans"),
        Action(type=ActionType.ANSWER, text="I give up", caption="give up"),
    ]
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)
    result = await runner.run(
        persona, StubPersonaAgent(persona, script), target_url, "sign up", sink, "run-decoy"
    )

    # A named .webm receipt was produced and PersonaResult points to it.
    assert result.video_path is not None
    assert result.video_path.endswith(".webm")
    assert Path(result.video_path).exists()

    # StepEvents reached the sink, each with a caption and a JPEG thumbnail data URI.
    step_events = [e for e in sink.events if isinstance(e, StepEvent)]
    assert len(step_events) >= 1
    for ev in step_events:
        assert ev.caption
        assert ev.thumbnail_b64.startswith("data:image/jpeg;base64,")

    # Lifecycle events present.
    assert any(isinstance(e, PersonaStarted) for e in sink.events)
    assert any(isinstance(e, PersonaFinished) for e in sink.events)


async def test_budget_exhaustion_yields_step_budget(browser, tmp_path, target_url):
    c = await _measure(browser, target_url)
    persona = make_persona(max_steps=2, deadline_s=60.0)
    # More actions than max_steps, with distinct captions (so stuck never trips).
    script = [
        Action(type=ActionType.CLICK, x=c["accept"][0], y=c["accept"][1], caption=f"click {i}")
        for i in range(6)
    ]
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)
    result = await runner.run(
        persona, StubPersonaAgent(persona, script), target_url, "sign up", sink, "run-budget"
    )
    assert result.outcome == PersonaOutcome.STEP_BUDGET
    assert len(result.steps) == 2


async def test_slow_decide_does_not_burn_persona_patience(browser, tmp_path, target_url):
    """decide() latency (Holo inference + rate-limiter queue) is infra time and must
    NOT count against deadline_s — only simulated user time does."""
    c = await _measure(browser, target_url)
    persona = make_persona(deadline_s=8.0)
    script = [
        Action(type=ActionType.CLICK, x=c["accept"][0], y=c["accept"][1], caption="accept cookies"),
    ]
    # Two decide() calls (click + final ANSWER) at 5s each = 10s of wall clock spent
    # deciding, > the 8s deadline. Simulated time is ~1 step (~4.5s), well under it.
    agent = StubPersonaAgent(persona, script, decide_delay_s=5.0)
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)
    result = await runner.run(persona, agent, target_url, "sign up", sink, "run-slow-decide")
    assert result.outcome == PersonaOutcome.SUCCESS
    assert result.duration_s < persona.deadline_s


async def test_sim_clock_trips_time_budget(browser, tmp_path, target_url):
    """The per-step think-time charge exhausts a tight deadline even when the
    model answers instantly — patience is simulated, not wall-clock."""
    c = await _measure(browser, target_url)
    persona = make_persona(max_steps=10, deadline_s=7.0)
    script = [
        Action(type=ActionType.CLICK, x=c["accept"][0], y=c["accept"][1], caption=f"click {i}")
        for i in range(6)
    ]
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)
    result = await runner.run(
        persona, StubPersonaAgent(persona, script), target_url, "sign up", sink, "run-sim-clock"
    )
    assert result.outcome == PersonaOutcome.TIME_BUDGET
    # ~4.5s of simulated time per step -> the 7s deadline trips on step 1 or 2.
    assert 1 <= len(result.steps) <= 2


async def test_dead_spot_clicks_detected_as_stuck(browser, tmp_path, target_url):
    """Near-identical clicks that visibly change nothing (e.g. tremor jitter around a
    dead spot) trip the stuck detector even though each caption differs."""
    persona = make_persona()
    script = [
        Action(type=ActionType.CLICK, x=5 + i, y=5 + i, caption=f"Clicking at ({5 + i}, {5 + i})")
        for i in range(4)
    ]
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)
    result = await runner.run(
        persona, StubPersonaAgent(persona, script), target_url, "sign up", sink, "run-dead-spot"
    )
    assert result.outcome == PersonaOutcome.STUCK


async def test_success_script_yields_success(browser, tmp_path, target_url):
    c = await _measure(browser, target_url)
    persona = make_persona()
    script = [
        Action(type=ActionType.CLICK, x=c["accept"][0], y=c["accept"][1], caption="accept cookies"),
        Action(type=ActionType.WRITE, x=c["email"][0], y=c["email"][1], text="me@work.com", caption="type email"),
        Action(type=ActionType.SCROLL, direction=ScrollDirection.DOWN, caption="scroll down"),
        # Let the wheel scroll settle before clicking at pre-measured coords —
        # a real (rate-limited) run always has seconds between steps.
        Action(type=ActionType.WAIT, seconds=0.4, caption="wait"),
        Action(type=ActionType.WRITE, x=c["promo"][0], y=c["promo"][1], text="LEAP50", caption="type promo"),
        Action(type=ActionType.CLICK, x=c["submit"][0], y=c["submit"][1], caption="create account"),
    ]
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path, success_predicate=_ok_visible)
    result = await runner.run(
        persona, StubPersonaAgent(persona, script), target_url, "sign up", sink, "run-success"
    )
    assert result.outcome == PersonaOutcome.SUCCESS
    finished = [e for e in sink.events if isinstance(e, PersonaFinished)]
    assert finished and finished[0].outcome == PersonaOutcome.SUCCESS
