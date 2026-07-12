"""Regression tests for Holo output parsing hardening.

Live Holo 3.1 was observed emitting key-dropped coordinate JSON —
``{"action": "click", "x": 426, 536}`` — which previously fell through to the
blind center-click fallback and stalled every persona at (w/2, h/2).
"""

from ghostpanel.engine.holo_client import _repair_json, parse_action
from ghostpanel_contracts import ActionType

W, H = 1280, 800


def test_repair_missing_y_key():
    assert _repair_json('{"action": "click", "x": 426, 536}') == (
        '{"action": "click", "x": 426, "y": 536}'
    )


def test_repair_missing_x_key():
    assert _repair_json('{"action": "click", 426, "y": 536}') == (
        '{"action": "click", "x": 426, "y": 536}'
    )


def test_repair_leaves_valid_json_alone():
    valid = '{"action": "click", "x": 426, "y": 536}'
    assert _repair_json(valid) == valid


def test_parse_key_dropped_click_denormalizes():
    # The exact live-observed malformation; 426/536 are 0-1000 normalized.
    action = parse_action('{"action": "click", "x": 426, 536}', W, H, normalize=True)
    assert action.type == ActionType.CLICK
    assert (action.x, action.y) == (round(426 / 1000 * W), round(536 / 1000 * H))


def test_parse_key_dropped_write_keeps_text():
    raw = '{"action": "write", "x": 300, 120, "text": "hello"}'
    action = parse_action(raw, W, H, normalize=True)
    assert action.type == ActionType.WRITE
    assert action.text == "hello"
    assert action.y == round(120 / 1000 * H)


def test_loose_number_click_fallback_prefers_numbers_over_center():
    action = parse_action("I will click the button at 426, 536.", W, H, normalize=True)
    assert action.type == ActionType.CLICK
    assert (action.x, action.y) == (round(426 / 1000 * W), round(536 / 1000 * H))
    assert action.text != "unparsed"


def test_unparseable_still_center_clicks():
    action = parse_action("no idea what to do", W, H, normalize=True)
    assert action.type == ActionType.CLICK
    assert (action.x, action.y) == (W // 2, H // 2)
    assert action.text == "unparsed"


def test_label_becomes_caption():
    raw = '{"action": "click", "x": 500, "y": 500, "label": "Accept cookies"}'
    action = parse_action(raw, W, H, normalize=True)
    assert action.caption == "Clicking Accept cookies"


def test_write_label_caption():
    raw = '{"action": "write", "x": 1, "y": 2, "text": "a@b.c", "label": "Email field"}'
    action = parse_action(raw, W, H, normalize=True)
    assert action.caption == "Typing 'a@b.c' into Email field"
