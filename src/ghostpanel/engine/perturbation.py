"""Pure perception/actuation perturbations (Agent 1).

GOLDEN RULE: every image transform returns an image with **exactly the input
dimensions**. Holo's smart_resize tokenizes whatever dims it receives, so as
long as dims never change, its returned coordinates are already true pixels
and no remap is needed. Blur/CVD only change pixel values; "downscale" is a
resize down **then back up in place**, so dims are unchanged too.

All functions are pure and unit-testable without Holo or a network.
"""

from __future__ import annotations

import io
from typing import Optional

import numpy as np
from daltonlens import simulate
from PIL import Image, ImageFilter

from ghostpanel_contracts import Action, CVDType, PersonaConfig

_CVD_DEFICIENCY = {
    CVDType.PROTAN: simulate.Deficiency.PROTAN,
    CVDType.DEUTAN: simulate.Deficiency.DEUTAN,
    CVDType.TRITAN: simulate.Deficiency.TRITAN,
}
# Machado 2009 supports arbitrary severities in [0, 1]; one shared simulator.
_CVD_SIMULATOR = simulate.Simulator_Machado2009()


def blur(img: Image.Image, sigma: float) -> Image.Image:
    """Gaussian blur (low visual acuity). Dims unchanged."""
    if sigma <= 0:
        return img
    return img.filter(ImageFilter.GaussianBlur(sigma))


def downscale_in_place(img: Image.Image, factor: float) -> Image.Image:
    """Resize to ``factor`` of the original then back up to the ORIGINAL size.
    Destroys high-frequency detail while keeping dimensions identical."""
    if factor >= 1.0 or factor <= 0:
        return img
    w, h = img.size
    small = img.resize((max(1, round(w * factor)), max(1, round(h * factor))), Image.BILINEAR)
    return small.resize((w, h), Image.BILINEAR)


def apply_cvd(img: Image.Image, cvd_type: CVDType, severity: float) -> Image.Image:
    """Colour-vision-deficiency simulation (DaltonLens Machado 2009).
    ``severity`` in [0, 1]; 0 returns the image untouched. Dims unchanged."""
    if severity <= 0:
        return img
    rgb = img.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    out = _CVD_SIMULATOR.simulate_cvd(arr, _CVD_DEFICIENCY[cvd_type], min(severity, 1.0))
    return Image.fromarray(out, mode="RGB")


def jitter_coords(
    x: int,
    y: int,
    sigma_px: float,
    w: int,
    h: int,
    rng: Optional[np.random.Generator] = None,
) -> tuple[int, int]:
    """Add gaussian noise (motor tremor) to a click point, clamped in-bounds
    to [0, w) x [0, h). ``rng`` is injectable for deterministic tests."""
    if sigma_px <= 0:
        return min(max(int(x), 0), w - 1), min(max(int(y), 0), h - 1)
    rng = rng if rng is not None else np.random.default_rng()
    dx, dy = rng.normal(0.0, sigma_px, size=2)
    jx = min(max(int(round(x + dx)), 0), w - 1)
    jy = min(max(int(round(y + dy)), 0), h - 1)
    return jx, jy


def perceive(png_bytes: bytes, persona: PersonaConfig) -> bytes:
    """Degrade a screenshot through the persona's perception channel.

    Applies, in order: downscale-in-place -> blur -> CVD (each only when the
    persona's field enables it: ``downscale_factor < 1``, ``blur_sigma > 0``,
    ``cvd_type`` set with ``cvd_severity > 0``). Returns PNG bytes with the
    SAME dimensions as the input; if no perception perturbation is active the
    input bytes are returned untouched (no re-encode).
    """
    has_downscale = 0 < persona.downscale_factor < 1.0
    has_blur = persona.blur_sigma > 0
    has_cvd = persona.cvd_type is not None and persona.cvd_severity > 0
    if not (has_downscale or has_blur or has_cvd):
        return png_bytes

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    original_size = img.size
    if has_downscale:
        img = downscale_in_place(img, persona.downscale_factor)
    if has_blur:
        img = blur(img, persona.blur_sigma)
    if has_cvd:
        img = apply_cvd(img, persona.cvd_type, persona.cvd_severity)
    assert img.size == original_size, "perturbation changed image dims (golden rule violated)"

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def actuate(
    action: Action,
    persona: PersonaConfig,
    w: int,
    h: int,
    rng: Optional[np.random.Generator] = None,
) -> Action:
    """Degrade an action through the persona's actuation channel.

    If the action carries coordinates and the persona has tremor, jitter the
    coords (clamped inside the ``w`` x ``h`` viewport). Actions without
    coordinates, or personas without tremor, pass through unchanged.
    """
    if action.x is None or action.y is None or persona.tremor_sigma_px <= 0:
        return action
    jx, jy = jitter_coords(action.x, action.y, persona.tremor_sigma_px, w, h, rng=rng)
    return action.model_copy(update={"x": jx, "y": jy})
