"""Perturbation unit tests: every transform changes pixels but never dims."""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ghostpanel.engine.perturbation import (
    actuate,
    apply_cvd,
    blur,
    downscale_in_place,
    jitter_coords,
    perceive,
)
from ghostpanel_contracts import Action, ActionType, CVDType, PersonaConfig

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def screenshot() -> Image.Image:
    return Image.open(FIXTURES / "sample_screenshot.png").convert("RGB")


@pytest.fixture()
def screenshot_png() -> bytes:
    return (FIXTURES / "sample_screenshot.png").read_bytes()


def _pixels_differ(a: Image.Image, b: Image.Image) -> bool:
    return not np.array_equal(np.asarray(a.convert("RGB")), np.asarray(b.convert("RGB")))


def test_blur_changes_pixels_preserves_size(screenshot):
    out = blur(screenshot, sigma=3.0)
    assert out.size == screenshot.size
    assert _pixels_differ(out, screenshot)


def test_downscale_in_place_changes_pixels_preserves_size(screenshot):
    out = downscale_in_place(screenshot, factor=0.4)
    assert out.size == screenshot.size
    assert _pixels_differ(out, screenshot)


def test_cvd_changes_pixels_preserves_size(screenshot):
    out = apply_cvd(screenshot, CVDType.DEUTAN, severity=0.9)
    assert out.size == screenshot.size
    assert _pixels_differ(out, screenshot)


def test_cvd_reduces_red_green_separation():
    img = Image.new("RGB", (64, 32))
    img.paste((220, 20, 20), (0, 0, 32, 32))    # red half
    img.paste((20, 200, 20), (32, 0, 64, 32))   # green half
    out = apply_cvd(img, CVDType.DEUTAN, severity=1.0)

    def separation(im):
        arr = np.asarray(im, dtype=float)
        left = arr[:, :32].reshape(-1, 3).mean(axis=0)
        right = arr[:, 32:].reshape(-1, 3).mean(axis=0)
        return np.linalg.norm(left - right)

    assert separation(out) < separation(img) * 0.5


def test_zero_severity_and_zero_sigma_are_noops(screenshot):
    assert not _pixels_differ(blur(screenshot, 0.0), screenshot)
    assert not _pixels_differ(downscale_in_place(screenshot, 1.0), screenshot)
    assert not _pixels_differ(apply_cvd(screenshot, CVDType.PROTAN, 0.0), screenshot)


def test_jitter_coords_in_bounds_and_spread():
    rng = np.random.default_rng(42)
    w, h, sigma = 640, 480, 14.0
    samples = np.array(
        [jitter_coords(320, 240, sigma, w, h, rng=rng) for _ in range(2000)], dtype=float
    )
    assert samples[:, 0].min() >= 0 and samples[:, 0].max() < w
    assert samples[:, 1].min() >= 0 and samples[:, 1].max() < h
    # spread roughly sigma (nothing clamps this far from the edges)
    assert 0.8 * sigma < samples[:, 0].std() < 1.2 * sigma
    assert 0.8 * sigma < samples[:, 1].std() < 1.2 * sigma


def test_jitter_coords_clamps_near_edges():
    rng = np.random.default_rng(0)
    for _ in range(500):
        x, y = jitter_coords(1, 479, 25.0, 640, 480, rng=rng)
        assert 0 <= x < 640 and 0 <= y < 480


def test_jitter_zero_sigma_identity():
    assert jitter_coords(100, 200, 0.0, 640, 480) == (100, 200)


def test_perceive_preserves_dims_and_degrades(screenshot_png):
    persona = PersonaConfig(
        id="p", name="p", blur_sigma=3.0, downscale_factor=0.5,
        cvd_type=CVDType.DEUTAN, cvd_severity=0.9,
    )
    out = perceive(screenshot_png, persona)
    original = Image.open(io.BytesIO(screenshot_png))
    degraded = Image.open(io.BytesIO(out))
    assert degraded.size == original.size          # GOLDEN RULE
    assert _pixels_differ(degraded, original)


def test_perceive_noop_returns_input_bytes(screenshot_png):
    persona = PersonaConfig(id="clean", name="clean")
    assert perceive(screenshot_png, persona) is screenshot_png


def test_actuate_jitters_tremor_persona():
    persona = PersonaConfig(id="t", name="t", tremor_sigma_px=14.0)
    action = Action(type=ActionType.CLICK, x=320, y=240)
    rng = np.random.default_rng(7)
    out = actuate(action, persona, 640, 480, rng=rng)
    assert (out.x, out.y) != (320, 240)
    assert 0 <= out.x < 640 and 0 <= out.y < 480
    assert action.x == 320 and action.y == 240     # input not mutated


def test_actuate_passthrough_without_tremor_or_coords():
    steady = PersonaConfig(id="s", name="s")
    click = Action(type=ActionType.CLICK, x=10, y=10)
    assert actuate(click, steady, 640, 480) is click

    tremor = PersonaConfig(id="t", name="t", tremor_sigma_px=14.0)
    scroll = Action(type=ActionType.SCROLL)
    assert actuate(scroll, tremor, 640, 480) is scroll
