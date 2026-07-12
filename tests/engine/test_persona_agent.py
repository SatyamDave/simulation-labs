"""HoloPersonaAgent tests — run with FakeHoloClient, no keys, no network."""

from pathlib import Path

from ghostpanel.engine.holo_client import FakeHoloClient, LiveHoloClient
from ghostpanel.engine.persona_agent import HoloPersonaAgent
from ghostpanel.engine.prompts import DEFAULT_TASK
from ghostpanel_contracts import (
    Action,
    ActionType,
    HoloClient,
    Observation,
    PersonaAgent,
    PersonaConfig,
    Viewport,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
PNG = (FIXTURES / "sample_screenshot.png").read_bytes()  # 640x480
VIEWPORT = Viewport(width=640, height=480)


def _obs(step: int = 0) -> Observation:
    return Observation(raw_png=PNG, viewport=VIEWPORT, step_index=step, url="https://x.test")


def _persona(**overrides) -> PersonaConfig:
    return PersonaConfig(id="test", name="Test", **overrides)


def test_protocol_conformance():
    fake = FakeHoloClient()
    live = LiveHoloClient(api_key="hk-test", base_url="https://api.hcompany.ai/v1/",
                          model="holo3-1-35b-a3b", rpm=10)
    agent = HoloPersonaAgent(_persona(), fake)
    assert isinstance(fake, HoloClient)
    assert isinstance(live, HoloClient)
    assert isinstance(agent, PersonaAgent)


async def test_decide_returns_in_viewport_action():
    agent = HoloPersonaAgent(_persona(), FakeHoloClient())
    action = await agent.decide(_obs(), ["TASK: Sign up for the newsletter"])
    assert isinstance(action, Action)
    assert action.type is ActionType.CLICK
    assert 0 <= action.x < VIEWPORT.width
    assert 0 <= action.y < VIEWPORT.height
    # Fake default = centre of the 640x480 screenshot
    assert (action.x, action.y) == (320, 240)


async def test_task_extracted_from_history_seed():
    fake = FakeHoloClient()
    agent = HoloPersonaAgent(_persona(), fake)
    await agent.decide(_obs(), ["TASK: Cancel my subscription", "Clicking Account"])
    call = fake.calls[-1]
    assert call["task"] == "Cancel my subscription"
    # the TASK seed must NOT leak into past-action history
    assert call["history"] == ["Clicking Account"]


async def test_task_fallback_when_seed_absent():
    fake = FakeHoloClient()
    agent = HoloPersonaAgent(_persona(), fake)
    await agent.decide(_obs(), [])
    assert fake.calls[-1]["task"] == DEFAULT_TASK


async def test_literacy_note_folded_into_task():
    fake = FakeHoloClient()
    agent = HoloPersonaAgent(_persona(literacy_note="Read the screen literally."), fake)
    await agent.decide(_obs(), ["TASK: Buy socks"])
    task = fake.calls[-1]["task"]
    assert task.startswith("Buy socks")
    assert "Read the screen literally." in task


async def test_tremor_persona_jitters_fake_coords():
    agent = HoloPersonaAgent(_persona(tremor_sigma_px=14.0), FakeHoloClient())
    history = ["TASK: anything"]
    results = [await agent.decide(_obs(i), history) for i in range(5)]
    assert any((a.x, a.y) != (320, 240) for a in results)  # P(all centre) ~ 1e-15
    for a in results:
        assert 0 <= a.x < VIEWPORT.width and 0 <= a.y < VIEWPORT.height


async def test_perception_persona_still_gets_valid_action():
    from ghostpanel_contracts import CVDType

    persona = _persona(blur_sigma=3.0, downscale_factor=0.5,
                       cvd_type=CVDType.DEUTAN, cvd_severity=0.9)
    agent = HoloPersonaAgent(persona, FakeHoloClient())
    action = await agent.decide(_obs(), ["TASK: anything"])
    # perturbed image keeps its dims, so the fake still sees 640x480
    assert (action.x, action.y) == (320, 240)


async def test_scripted_actions_consumed_in_order_then_default():
    scripted = [
        Action(type=ActionType.SCROLL, caption="Scrolling down"),
        Action(type=ActionType.ANSWER, text="done", caption="Finished: done"),
    ]
    agent = HoloPersonaAgent(_persona(), FakeHoloClient(scripted_actions=scripted))
    history = ["TASK: anything"]
    assert (await agent.decide(_obs(0), history)).type is ActionType.SCROLL
    assert (await agent.decide(_obs(1), history)).type is ActionType.ANSWER
    fallback = await agent.decide(_obs(2), history)
    assert fallback.type is ActionType.CLICK and (fallback.x, fallback.y) == (320, 240)
