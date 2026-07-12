"""Unit tests for detect.py — stuck-loop and screen-change detection (no browser)."""

from __future__ import annotations

import io

from PIL import Image

from ghostpanel.runner.detect import NO_CHANGE_NOTE, frames_similar, is_stuck


def _png(color: tuple[int, int, int], size=(128, 96)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# --- is_stuck ---------------------------------------------------------------
def test_identical_captions_are_stuck():
    assert is_stuck(["Clicking at (10, 10)"] * 3)


def test_annotation_does_not_hide_identical_captions():
    history = [
        "Clicking at (10, 10)",
        "Clicking at (10, 10)" + NO_CHANGE_NOTE,
        "Clicking at (10, 10)" + NO_CHANGE_NOTE,
    ]
    assert is_stuck(history)


def test_jittered_dead_spot_clicks_are_stuck():
    history = [
        "Clicking at (100, 100)" + NO_CHANGE_NOTE,
        "Clicking at (108, 95)" + NO_CHANGE_NOTE,
        "Clicking at (103, 104)" + NO_CHANGE_NOTE,
    ]
    assert is_stuck(history)


def test_jittered_clicks_that_change_the_screen_are_not_stuck():
    history = [
        "Clicking at (100, 100)",
        "Clicking at (108, 95)",
        "Clicking at (103, 104)",
    ]
    assert is_stuck(history) is False


def test_far_apart_clicks_are_not_stuck():
    history = [
        "Clicking at (100, 100)" + NO_CHANGE_NOTE,
        "Clicking at (400, 300)" + NO_CHANGE_NOTE,
        "Clicking at (700, 500)" + NO_CHANGE_NOTE,
    ]
    assert is_stuck(history) is False


def test_varied_actions_are_not_stuck():
    assert is_stuck(["Clicking at (10, 10)", "Scrolling down", "Typing 'hi'"]) is False


def test_short_history_is_not_stuck():
    assert is_stuck(["Clicking at (10, 10)"] * 2) is False


# --- frames_similar ---------------------------------------------------------
def test_identical_frames_similar():
    png = _png((250, 250, 250))
    assert frames_similar(png, bytes(png)) is True


def test_different_frames_not_similar():
    assert frames_similar(_png((255, 255, 255)), _png((0, 0, 0))) is False


def test_empty_frames_not_similar():
    assert frames_similar(b"", _png((0, 0, 0))) is False
