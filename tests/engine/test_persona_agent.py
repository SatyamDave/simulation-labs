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


def test_rate_limiter_paces_evenly_with_tiny_burst():
    # The hosted API has NO burst allowance (429 + retry-after on bursts), so the
    # bucket must hold at most 2 tokens regardless of RPM.
    async def run():
        rl = RateLimiter(rpm=60)
        assert rl._capacity <= 2.0
        await rl.acquire()
        await rl.acquire()
        # bucket now near empty; internal tokens < 1
        assert rl._tokens < 1.0
    asyncio.run(run())


def test_transport_downscale_shrinks_and_reports_scale():
    from ghostpanel.engine.perturbation import transport_downscale
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (1280, 800), (200, 200, 200)).save(buf, format="PNG")
    small, scale = transport_downscale(buf.getvalue(), 1024)
    assert scale == 1024 / 1280
    assert Image.open(io.BytesIO(small)).size == (1024, 640)

    # No-op when already narrow enough — identical bytes, scale 1.0.
    same, scale2 = transport_downscale(buf.getvalue(), 1280)
    assert scale2 == 1.0 and same == buf.getvalue()


def test_decide_rescales_downscaled_coords_for_sent_image_backend(monkeypatch):
    # Viewport 1280x800, transport cap 1024 -> scale 0.8. For a backend whose
    # coords are relative to the SENT image (Holo/Gemini), a click at (400, 240)
    # in sent-image space must come back as (500, 300) in viewport space.
    from PIL import Image
    import io

    class _SentImageFake(FakeHoloClient):
        coords_relative_to_sent_image = True

    monkeypatch.setenv("HAI_IMG_MAX_W", "1024")
    buf = io.BytesIO()
    Image.new("RGB", (1280, 800), (230, 230, 230)).save(buf, format="PNG")
    obs = Observation(
        raw_png=buf.getvalue(),
        viewport=Viewport(width=1280, height=800),
        step_index=0,
    )
    fake = _SentImageFake([Action(type=ActionType.CLICK, x=400, y=240, caption="c")])
    agent = HoloPersonaAgent(PersonaConfig(id="p", name="P"), fake, task="t")
    act = asyncio.run(agent.decide(obs, []))
    assert (act.x, act.y) == (500, 300)


def test_decide_executes_true_pixel_backend_coords_verbatim(monkeypatch):
    # FakeHoloClient/Echo return TRUE viewport pixels — the agent must NOT
    # downscale+rescale them. A scripted click at (400, 240) executes verbatim
    # even at the default 1280 viewport where transport downscale would fire.
    from PIL import Image
    import io

    monkeypatch.setenv("HAI_IMG_MAX_W", "1024")
    buf = io.BytesIO()
    Image.new("RGB", (1280, 800), (230, 230, 230)).save(buf, format="PNG")
    obs = Observation(
        raw_png=buf.getvalue(),
        viewport=Viewport(width=1280, height=800),
        step_index=0,
    )
    fake = FakeHoloClient([Action(type=ActionType.CLICK, x=400, y=240, caption="c")])
    agent = HoloPersonaAgent(PersonaConfig(id="p", name="P"), fake, task="t")
    act = asyncio.run(agent.decide(obs, []))
    assert (act.x, act.y) == (400, 240)


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


def test_parse_action_malformed_click_missing_y_key():
    """Live Holo sometimes drops the "y" key (observed verbatim from the API).
    The salvage path must recover the pair instead of center-clicking."""
    raw = '\n\n{"action": "click", "x": 426, 536}'
    act = parse_action(raw, 1280, 800, normalize=True)
    assert act.type == ActionType.CLICK
    # 426/1000*1280=545, 536/1000*800=429 (denormalized like well-formed output)
    assert (act.x, act.y) == (545, 429)
    # Well-formed pixel-space salvage (normalize=False) passes through clamped.
    act2 = parse_action('{"action":"tap", "x": 12, 34}', 640, 480)
    assert act2.type == ActionType.CLICK and (act2.x, act2.y) == (12, 34)
