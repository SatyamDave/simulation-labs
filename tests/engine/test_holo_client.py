"""Holo client tests: response parsing, rate limiter, and (opt-in) live smoke.

Everything runs offline except the live-smoke test at the bottom, which only
runs when HAI_API_KEY is set.
"""

import asyncio
import os
import time
from pathlib import Path

import pytest

from ghostpanel.engine.holo_client import (
    AsyncTokenBucket,
    FakeHoloClient,
    parse_click_response,
    parse_navigation_response,
    png_size,
)
from ghostpanel_contracts import ActionType, ScrollDirection

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
PNG = (FIXTURES / "sample_screenshot.png").read_bytes()
SIZE = (640, 480)


def test_png_size():
    assert png_size(PNG) == SIZE
    assert png_size(b"not a png") is None


# --- localizer parsing ------------------------------------------------------
def test_parse_click_text():
    assert parse_click_response("Click(100, 200)", SIZE) == (100, 200)
    assert parse_click_response("Sure! Click(12, 34).", SIZE) == (12, 34)


def test_parse_click_json():
    assert parse_click_response('{"action": "click", "x": 55, "y": 66}', SIZE) == (55, 66)


def test_parse_click_normalized_rescaled():
    # legacy 0-1000 normalized coords: outside the 640x480 image but <= 1000
    x, y = parse_click_response("Click(500, 900)", SIZE)
    assert (x, y) == (320, 432)


def test_parse_click_garbage_raises():
    with pytest.raises(ValueError):
        parse_click_response("I cannot find that element.", SIZE)


# --- navigation parsing -----------------------------------------------------
def test_parse_navigation_json_every_action():
    cases = [
        ('{"thought": "t", "action": "click", "x": 10, "y": 20, "element": "Sign up"}',
         ActionType.CLICK),
        ('{"action": "write", "text": "hello", "x": 5, "y": 6}', ActionType.WRITE),
        ('{"action": "scroll", "direction": "down"}', ActionType.SCROLL),
        ('{"action": "go_back"}', ActionType.GO_BACK),
        ('{"action": "refresh"}', ActionType.REFRESH),
        ('{"action": "wait", "seconds": 2}', ActionType.WAIT),
        ('{"action": "goto", "url": "https://example.com"}', ActionType.GOTO),
        ('{"action": "restart"}', ActionType.RESTART),
        ('{"action": "answer", "text": "42"}', ActionType.ANSWER),
    ]
    for raw, expected in cases:
        action = parse_navigation_response(raw, SIZE)
        assert action.type is expected, raw
        assert action.raw == raw
        assert action.caption

    click = parse_navigation_response(cases[0][0], SIZE)
    assert (click.x, click.y) == (10, 20)
    assert "Sign up" in click.caption

    write = parse_navigation_response(cases[1][0], SIZE)
    assert write.text == "hello" and (write.x, write.y) == (5, 6)

    scroll = parse_navigation_response(cases[2][0], SIZE)
    assert scroll.direction is ScrollDirection.DOWN

    wait = parse_navigation_response(cases[5][0], SIZE)
    assert wait.seconds == 2

    goto = parse_navigation_response(cases[6][0], SIZE)
    assert goto.url == "https://example.com"

    answer = parse_navigation_response(cases[8][0], SIZE)
    assert answer.text == "42"


def test_parse_navigation_cookbook_nested_shape():
    raw = ('{"note": "", "thought": "click it", '
           '"action": {"action": "click_element", "element": "Buy", "x": 100, "y": 150}}')
    action = parse_navigation_response(raw, SIZE)
    assert action.type is ActionType.CLICK
    assert (action.x, action.y) == (100, 150)


def test_parse_navigation_json_in_code_fence():
    raw = 'Here you go:\n```json\n{"action": "scroll", "direction": "up"}\n```'
    action = parse_navigation_response(raw, SIZE)
    assert action.type is ActionType.SCROLL and action.direction is ScrollDirection.UP


def test_parse_navigation_freeform_fallbacks():
    assert parse_navigation_response("I will Click(300, 40) now", SIZE).type is ActionType.CLICK
    assert parse_navigation_response("Let's scroll down a bit", SIZE).type is ActionType.SCROLL
    assert parse_navigation_response("go back to the previous page", SIZE).type is ActionType.GO_BACK

    unparseable = parse_navigation_response("¯\\_(ツ)_/¯", SIZE)
    assert unparseable.type is ActionType.WAIT
    assert unparseable.seconds == 1.0


def test_parse_navigation_clamps_out_of_range_pixel_coords():
    # > 1000 so not normalized: clamp inside the image instead
    action = parse_navigation_response('{"action": "click", "x": 5000, "y": 10}', SIZE)
    assert action.x == SIZE[0] - 1 and action.y == 10


# --- rate limiter -----------------------------------------------------------
async def test_token_bucket_burst_within_capacity_is_instant():
    bucket = AsyncTokenBucket(rpm=2)  # capacity 2, starts full
    t0 = time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    assert time.monotonic() - t0 < 0.5


async def test_token_bucket_throttles_beyond_capacity():
    bucket = AsyncTokenBucket(rpm=600)
    bucket._tokens = 1.0   # pretend the burst budget is nearly spent
    bucket.rate = 10.0     # refill 10 tokens/s so the test stays fast
    t0 = time.monotonic()
    await asyncio.gather(bucket.acquire(), bucket.acquire(), bucket.acquire())
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.15  # 2 extra tokens at 10 tokens/s ~ 0.2s


# --- FakeHoloClient stable contract ----------------------------------------
async def test_fake_default_center_click_and_call_log():
    fake = FakeHoloClient()
    action = await fake.navigate(PNG, "task", ["a"])
    assert action.type is ActionType.CLICK and (action.x, action.y) == (320, 240)
    assert action.caption == "Clicking the centre of the page"
    assert await fake.localize(PNG, "the button") == (320, 240)
    assert [c["method"] for c in fake.calls] == ["navigate", "localize"]


async def test_fake_non_png_falls_back_to_default_viewport():
    fake = FakeHoloClient()
    action = await fake.navigate(b"jpeg?", "task", [])
    assert (action.x, action.y) == (640, 400)  # centre of (1280, 800)


# --- live smoke (manual; needs HAI_API_KEY) ---------------------------------
@pytest.mark.skipif(not os.getenv("HAI_API_KEY"), reason="HAI_API_KEY not set")
async def test_live_localize_smoke():
    from ghostpanel.engine.holo_client import LiveHoloClient

    client = LiveHoloClient(
        api_key=os.environ["HAI_API_KEY"],
        base_url=os.getenv("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
        model=os.getenv("HAI_MODEL", "holo3-1-35b-a3b"),
        rpm=float(os.getenv("HAI_RPM", "10")),
    )
    x, y = await client.localize(PNG, "the most prominent button or link on the page")
    assert 0 <= x < SIZE[0] and 0 <= y < SIZE[1]
