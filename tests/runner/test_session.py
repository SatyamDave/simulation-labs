"""PlaywrightSessionRunner end-to-end against fixtures/hostile_form.html.

Hermetic: headless Chromium + file:// pages only. No engine, no Holo, no keys.
The success script's coordinates are measured on a scout page by replaying the
exact same actions with execute_action, so the recorded session — starting from
the identical initial state — clicks the same true viewport pixels.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import io

from ghostpanel.runner.detect import is_stuck
from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.runner.testing import CollectingEventSink, StubPersonaAgent
from ghostpanel.runner.thumbnail import to_thumb_data_uri
from ghostpanel.runner.execute import execute_action
from ghostpanel_contracts import (
    Action,
    ActionType,
    EventSink,
    PersonaAgent,
    PersonaConfig,
    PersonaFinished,
    PersonaOutcome,
    PersonaStarted,
    ScrollDirection,
    SessionRunner,
    StepEvent,
)

TASK = "Sign up for a free trial"


def make_persona(**overrides) -> PersonaConfig:
    base = dict(id="test-persona", name="Testy McTestface", max_steps=12, deadline_s=60.0)
    base.update(overrides)
    return PersonaConfig(**base)


async def _center(page, selector: str) -> tuple[int, int]:
    box = await page.locator(selector).bounding_box()
    assert box is not None, f"no bounding box for {selector}"
    return int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)


async def build_success_script(browser, url: str) -> list[Action]:
    """Measure true viewport pixel targets by replaying the script on a scout page."""
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()
    await page.goto(url)
    script: list[Action] = []

    async def step(action: Action) -> None:
        script.append(action)
        await execute_action(page, action, target_url=url)

    x, y = await _center(page, "#cookie .btn-decoy")
    await step(Action(type=ActionType.CLICK, x=x, y=y, caption="Accepting the cookie wall"))

    x, y = await _center(page, "#email")
    await step(
        Action(type=ActionType.WRITE, x=x, y=y, text="jane@work.com", caption="Typing my email")
    )

    await step(
        Action(type=ActionType.SCROLL, direction=ScrollDirection.DOWN, caption="Scrolling down")
    )
    await step(
        Action(type=ActionType.WAIT, seconds=0.5, caption="Waiting for the page to settle")
    )
    await page.wait_for_selector("#promo", state="visible")

    # Measure the submit button BEFORE the promo WRITE: its trailing Enter
    # submits the (now valid) form, which hides it on the scout page.
    bx, by = await _center(page, ".btn-real")
    x, y = await _center(page, "#promo")
    await step(
        Action(type=ActionType.WRITE, x=x, y=y, text="LEAP-2026", caption="Typing the promo code")
    )
    script.append(
        Action(type=ActionType.CLICK, x=bx, y=by, caption="Clicking Create account")
    )
    script.append(Action(type=ActionType.WAIT, seconds=0.3, caption="Looking around"))

    await context.close()
    return script


# ---------------------------------------------------------------------------
# Contract conformance
# ---------------------------------------------------------------------------
async def test_registry_classes_satisfy_protocols(browser, tmp_path):
    assert isinstance(PlaywrightSessionRunner(browser, tmp_path), SessionRunner)
    assert isinstance(CollectingEventSink(), EventSink)
    assert isinstance(StubPersonaAgent(make_persona(), []), PersonaAgent)


# ---------------------------------------------------------------------------
# The success path (the important one)
# ---------------------------------------------------------------------------
async def test_success_run_produces_result_events_and_video(browser, tmp_path, hostile_form_url):
    script = await build_success_script(browser, hostile_form_url)
    persona = make_persona()
    agent = StubPersonaAgent(persona, script)
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)

    result = await runner.run(persona, agent, hostile_form_url, TASK, sink, "run-success")

    assert result.outcome is PersonaOutcome.SUCCESS
    assert result.persona_id == persona.id
    assert result.failure_coords is None and result.failure_step is None
    assert result.duration_s > 0
    assert len(result.steps) >= 5

    # Video receipt: a named .webm exists and video_path points at it.
    assert result.video_path is not None and result.video_path.endswith(".webm")
    video = Path(result.video_path)
    assert video.is_file() and video.stat().st_size > 0
    assert video.parent == tmp_path / "run-success"

    # Event stream: PersonaStarted, one StepEvent per step, PersonaFinished.
    assert isinstance(sink.events[0], PersonaStarted)
    step_events = [e for e in sink.events if isinstance(e, StepEvent)]
    assert len(step_events) == len(result.steps)
    for ev in step_events:
        assert ev.caption
        assert ev.thumbnail_b64.startswith("data:image/jpeg;base64,")
    finished = sink.events[-1]
    assert isinstance(finished, PersonaFinished)
    assert finished.outcome is PersonaOutcome.SUCCESS
    assert finished.steps_survived == len(result.steps)

    # Frozen convention: history is seeded with the task before the 1st decide.
    assert agent.seen_histories[0][0] == f"TASK: {TASK}"


# ---------------------------------------------------------------------------
# Failure outcomes
# ---------------------------------------------------------------------------
async def test_step_budget_exhaustion(browser, tmp_path, hostile_form_url):
    # Alternating captions never trip the stuck detector; the budget runs out.
    script = [
        Action(type=ActionType.SCROLL, direction=ScrollDirection.DOWN, caption="Scrolling down"),
        Action(type=ActionType.SCROLL, direction=ScrollDirection.UP, caption="Scrolling back up"),
    ]
    persona = make_persona(max_steps=4)
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)

    result = await runner.run(
        persona, StubPersonaAgent(persona, script), hostile_form_url, TASK, sink, "run-budget"
    )

    assert result.outcome is PersonaOutcome.STEP_BUDGET
    assert len(result.steps) == 4
    assert result.failure_step == 3  # scrolls have no coords; last step index
    assert "step budget" in result.failure_reason
    assert result.video_path is not None and Path(result.video_path).is_file()
    finished = sink.events[-1]
    assert isinstance(finished, PersonaFinished)
    assert finished.outcome is PersonaOutcome.STEP_BUDGET
    assert finished.steps_survived == 4


async def test_stuck_detector_records_failure_coords(browser, tmp_path, hostile_form_url):
    script = [Action(type=ActionType.CLICK, x=640, y=400, caption="Clicking the same spot")]
    persona = make_persona(max_steps=10)
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)

    result = await runner.run(
        persona, StubPersonaAgent(persona, script), hostile_form_url, TASK, sink, "run-stuck"
    )

    assert result.outcome is PersonaOutcome.STUCK
    assert result.failure_coords == (640, 400)
    assert result.failure_step is not None
    assert "repeated" in result.failure_reason
    assert len(result.steps) < 10  # gave up well before the budget


async def test_time_budget_deadline(browser, tmp_path, hostile_form_url):
    script = [Action(type=ActionType.WAIT, seconds=5, caption="Staring at the page")]
    persona = make_persona(deadline_s=1.5, max_steps=50)
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)

    result = await runner.run(
        persona, StubPersonaAgent(persona, script), hostile_form_url, TASK, sink, "run-time"
    )

    assert result.outcome is PersonaOutcome.TIME_BUDGET
    assert "time budget" in result.failure_reason
    assert result.duration_s < 30
    assert isinstance(sink.events[-1], PersonaFinished)


async def test_unreachable_target_is_an_error(browser, tmp_path):
    persona = make_persona(deadline_s=10.0)
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(browser, tmp_path)

    result = await runner.run(
        persona,
        StubPersonaAgent(persona, []),
        "http://127.0.0.1:1/nope",  # connection refused instantly; no network leaves the box
        TASK,
        sink,
        "run-error",
    )

    assert result.outcome is PersonaOutcome.ERROR
    assert result.failure_reason
    assert result.steps == []
    finished = sink.events[-1]
    assert isinstance(finished, PersonaFinished)
    assert finished.outcome is PersonaOutcome.ERROR


# ---------------------------------------------------------------------------
# Success predicate override
# ---------------------------------------------------------------------------
async def test_custom_success_predicate_overrides_default(browser, tmp_path, hostile_form_url):
    async def instant_success(page) -> bool:
        return True

    script = [Action(type=ActionType.WAIT, seconds=0.1, caption="Blinking")]
    persona = make_persona()
    runner = PlaywrightSessionRunner(browser, tmp_path, success_predicate=instant_success)

    result = await runner.run(
        persona,
        StubPersonaAgent(persona, script),
        hostile_form_url,
        TASK,
        CollectingEventSink(),
        "run-predicate",
    )

    assert result.outcome is PersonaOutcome.SUCCESS
    assert len(result.steps) == 1


# ---------------------------------------------------------------------------
# Small helper units (no browser)
# ---------------------------------------------------------------------------
def test_is_stuck_ignores_task_seed_and_needs_a_full_window():
    assert not is_stuck(["TASK: sign up", "click A", "click A"])
    assert is_stuck(["TASK: sign up", "click A", "click A", "click A"])
    assert not is_stuck(["TASK: sign up", "click A", "click B", "click A"])
    assert not is_stuck(["TASK: sign up", "", "", ""])  # empty captions carry no signal


def test_thumbnail_is_a_small_jpeg_data_uri():
    buf = io.BytesIO()
    Image.new("RGB", (1280, 800), (200, 30, 30)).save(buf, format="PNG")
    uri = to_thumb_data_uri(buf.getvalue(), max_w=320)
    assert uri.startswith("data:image/jpeg;base64,")
    import base64

    jpeg = base64.b64decode(uri.split(",", 1)[1])
    thumb = Image.open(io.BytesIO(jpeg))
    assert thumb.width == 320 and thumb.height == 200
    assert len(jpeg) < 60_000
