"""HoloPersonaAgent + FakeHoloClient + parser tests."""

from __future__ import annotations

import asyncio
from pathlib import Path


from ghostpanel.engine.holo_client import (
    FakeHoloClient,
    LiveHoloClient,
    RateLimiter,
    parse_action,
    parse_click,
)
from ghostpanel.engine.persona_agent import HoloPersonaAgent
from ghostpanel_contracts import (
    Action,
    ActionType,
    HoloClient,
    Observation,
    PersonaAgent,
    PersonaConfig,
    ScrollDirection,
    Viewport,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "sample_screenshot.png"


def _obs() -> Observation:
    return Observation(
        raw_png=FIXTURE.read_bytes(),
        viewport=Viewport(width=640, height=480),
        step_index=0,
    )


def test_isinstance_protocols():
    fake = FakeHoloClient()
    live = LiveHoloClient(api_key="x", base_url="http://localhost/v1/", model="m", rpm=10)
    agent = HoloPersonaAgent(PersonaConfig(id="p", name="P"), fake)
    assert isinstance(fake, HoloClient)
    assert isinstance(live, HoloClient)
    assert isinstance(agent, PersonaAgent)


def test_fake_default_center_click():
    fake = FakeHoloClient()
    act = asyncio.run(fake.navigate(FIXTURE.read_bytes(), "task", []))
    assert act.type == ActionType.CLICK
    assert act.x == 320 and act.y == 240


def test_fake_scripted_actions_fifo():
    scripted = [
        Action(type=ActionType.CLICK, x=10, y=20, caption="a"),
        (55, 66),
        {"action": "scroll", "direction": "down"},
    ]
    fake = FakeHoloClient(scripted)
    png = FIXTURE.read_bytes()
    a1 = asyncio.run(fake.navigate(png, "t", []))
    a2 = asyncio.run(fake.navigate(png, "t", []))
    a3 = asyncio.run(fake.navigate(png, "t", []))
    assert (a1.x, a1.y) == (10, 20)
    assert (a2.x, a2.y) == (55, 66)
    assert a3.type == ActionType.SCROLL and a3.direction == ScrollDirection.DOWN


def test_decide_returns_in_viewport_action():
    fake = FakeHoloClient([Action(type=ActionType.CLICK, x=300, y=200, caption="c")])
    agent = HoloPersonaAgent(PersonaConfig(id="p", name="P"), fake, task="do it")
    act = asyncio.run(agent.decide(_obs(), []))
    assert isinstance(act, Action)
    assert 0 <= act.x < 640 and 0 <= act.y < 480
    assert (act.x, act.y) == (300, 200)


def test_decide_tremor_moves_coords():
    persona = PersonaConfig(id="t", name="T", tremor_sigma_px=14.0)
    # Same raw coords every call; tremor should perturb at least once.
    moved = False
    for _ in range(25):
        fake = FakeHoloClient([Action(type=ActionType.CLICK, x=300, y=200, caption="c")])
        agent = HoloPersonaAgent(persona, fake, task="t")
        act = asyncio.run(agent.decide(_obs(), []))
        assert 0 <= act.x < 640 and 0 <= act.y < 480
        if (act.x, act.y) != (300, 200):
            moved = True
    assert moved


def test_rate_limiter_allows_burst_then_blocks(monkeypatch):
    async def run():
        rl = RateLimiter(rpm=60)  # 1 token/sec, capacity 60
        # capacity full -> many acquires should be instant
        for _ in range(60):
            await rl.acquire()
        # bucket now near empty; internal tokens < 1
        assert rl._tokens < 1.0
    asyncio.run(run())


# ---- parser tests ----
def test_parse_click_shortform():
    assert parse_click("Some text Click(123, 456) end") == (123, 456)


def test_parse_action_json_click():
    act = parse_action('{"action": "click", "x": 12, "y": 34}', 640, 480)
    assert act.type == ActionType.CLICK and (act.x, act.y) == (12, 34)
    assert "Clicking" in act.caption


def test_parse_action_json_write():
    act = parse_action('{"action":"write","x":5,"y":6,"text":"hi"}', 640, 480)
    assert act.type == ActionType.WRITE and act.text == "hi"


def test_parse_action_json_scroll():
    act = parse_action('{"action":"scroll","direction":"up"}', 640, 480)
    assert act.type == ActionType.SCROLL and act.direction == ScrollDirection.UP


def test_parse_action_json_answer():
    act = parse_action('{"action":"answer","text":"finished"}', 640, 480)
    assert act.type == ActionType.ANSWER and act.text == "finished"


def test_parse_action_clickform_fallback():
    act = parse_action("I will Click(99, 88) now", 640, 480)
    assert act.type == ActionType.CLICK and (act.x, act.y) == (99, 88)


def test_parse_action_coordinate_list():
    act = parse_action('{"action":"click","coordinate":[7,8]}', 640, 480)
    assert (act.x, act.y) == (7, 8)


def test_parse_action_unparseable_center():
    act = parse_action("total gibberish no action here", 640, 480)
    assert act.type == ActionType.CLICK and (act.x, act.y) == (320, 240)


def test_parse_action_goto():
    act = parse_action('{"action":"goto","url":"https://x.com"}', 640, 480)
    assert act.type == ActionType.GOTO and act.url == "https://x.com"
    assert act.x is None
