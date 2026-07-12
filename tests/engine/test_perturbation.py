"""Perturbation unit tests. Golden rule: dimensions never change."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ghostpanel.engine import perturbation as pert
from ghostpanel_contracts import Action, ActionType, CVDType, PersonaConfig

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "sample_screenshot.png"


@pytest.fixture
def sample_img() -> Image.Image:
    return Image.open(FIXTURE).convert("RGB")


@pytest.fixture
def sample_png() -> bytes:
    return FIXTURE.read_bytes()


def _pixels_differ(a: Image.Image, b: Image.Image) -> bool:
    return not np.array_equal(np.asarray(a.convert("RGB")), np.asarray(b.convert("RGB")))


def test_blur_changes_pixels_keeps_size(sample_img):
    out = pert.blur(sample_img, sigma=3.0)
    assert out.size == sample_img.size
    assert _pixels_differ(out, sample_img)


def test_downscale_changes_pixels_keeps_size(sample_img):
    out = pert.downscale_in_place(sample_img, factor=0.3)
    assert out.size == sample_img.size
    assert _pixels_differ(out, sample_img)


def test_cvd_changes_pixels_keeps_size(sample_img):
    out = pert.apply_cvd(sample_img, CVDType.DEUTAN, severity=0.9)
    assert out.size == sample_img.size
    assert _pixels_differ(out, sample_img)


def test_cvd_reduces_red_green_separation():
    # A canvas split red | green. Deuteranopia should pull them closer together.
    w, h = 64, 32
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, : w // 2] = [220, 20, 20]   # red
    arr[:, w // 2 :] = [20, 200, 20]   # green
    img = Image.fromarray(arr, "RGB")

    def rg_gap(im: Image.Image) -> float:
        a = np.asarray(im.convert("RGB"), dtype=np.float64)
        left = a[:, : w // 2].mean(axis=(0, 1))
        right = a[:, w // 2 :].mean(axis=(0, 1))
        return float(np.linalg.norm(left - right))

    before = rg_gap(img)
    after = rg_gap(pert.apply_cvd(img, CVDType.DEUTAN, severity=0.9))
    assert after < before


def test_jitter_in_bounds_and_spread():
    rng = np.random.default_rng(0)
    w, h = 200, 100
    samples = [pert.jitter_coords(100, 50, 10.0, w, h, rng=rng) for _ in range(500)]
    xs = np.array([s[0] for s in samples])
    ys = np.array([s[1] for s in samples])
    assert xs.min() >= 0 and xs.max() < w
    assert ys.min() >= 0 and ys.max() < h
    # spread should be nonzero and roughly the requested sigma order of magnitude
    assert xs.std() > 3.0 and ys.std() > 3.0


def test_jitter_zero_sigma_is_identity():
    assert pert.jitter_coords(37, 88, 0.0, 200, 200) == (37, 88)


def test_perceive_preserves_dims(sample_png):
    persona = PersonaConfig(
        id="lv", name="LowVision", blur_sigma=3.0, downscale_factor=0.5,
        cvd_type=CVDType.DEUTAN, cvd_severity=0.8,
    )
    out = pert.perceive(sample_png, persona)
    orig = Image.open(io.BytesIO(sample_png))
    new = Image.open(io.BytesIO(out))
    assert new.size == orig.size
    assert _pixels_differ(new, orig)


def test_perceive_baseline_keeps_size(sample_png):
    persona = PersonaConfig(id="base", name="Base")
    out = pert.perceive(sample_png, persona)
    assert Image.open(io.BytesIO(out)).size == Image.open(io.BytesIO(sample_png)).size


def test_actuate_jitters_when_tremor():
    persona = PersonaConfig(id="t", name="T", tremor_sigma_px=14.0)
    action = Action(type=ActionType.CLICK, x=100, y=100, caption="c")
    moved = 0
    for _ in range(20):
        out = pert.actuate(action, persona, 640, 480)
        if (out.x, out.y) != (100, 100):
            moved += 1
        assert 0 <= out.x < 640 and 0 <= out.y < 480
    assert moved > 0


def test_actuate_no_tremor_is_identity_coords():
    persona = PersonaConfig(id="p", name="P")
    action = Action(type=ActionType.CLICK, x=50, y=60, caption="c")
    out = pert.actuate(action, persona, 640, 480)
    assert (out.x, out.y) == (50, 60)


def test_actuate_non_click_untouched():
    persona = PersonaConfig(id="p", name="P", tremor_sigma_px=14.0)
    action = Action(type=ActionType.SCROLL, caption="scroll")
    out = pert.actuate(action, persona, 640, 480)
    assert out.x is None and out.y is None
