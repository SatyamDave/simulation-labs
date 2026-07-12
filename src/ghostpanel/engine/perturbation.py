"""Pure perception/actuation perturbations.

GOLDEN RULE: every image transform returns an image whose ``.size`` is EQUAL to
the input's. Holo tokenizes at the image's dimensions (smart_resize); if we keep
dimensions constant we never have to remap the coordinates it returns. Blur/CVD
change pixel *values* only; downscale resizes down then back up in place.

Nothing here touches the network — all functions are deterministic given their
inputs (jitter takes an optional rng) and are unit-testable in isolation.
"""

from __future__ import annotations

import io

import numpy as np
from daltonlens import simulate
from PIL import Image, ImageFilter

from ghostpanel_contracts import Action, CVDType, PersonaConfig

_CVD_MAP = {
    CVDType.PROTAN: simulate.Deficiency.PROTAN,
    CVDType.DEUTAN: simulate.Deficiency.DEUTAN,
    CVDType.TRITAN: simulate.Deficiency.TRITAN,
}

# One simulator instance is fine to reuse (stateless matrices).
_CVD_SIM = simulate.Simulator_Machado2009()


# ---------------------------------------------------------------------------
# Image transforms (dimension-preserving)
# ---------------------------------------------------------------------------
def blur(img: Image.Image, sigma: float) -> Image.Image:
    """Gaussian blur. Returns a new image with identical dimensions."""
    if sigma <= 0:
        return img.copy()
    return img.filter(ImageFilter.GaussianBlur(radius=float(sigma)))


def downscale_in_place(img: Image.Image, factor: float) -> Image.Image:
    """Resize down by ``factor`` then back up to the original size.

    Loses high-frequency detail (low acuity) while keeping dimensions constant.
    ``factor`` in (0, 1); 1.0 (or >=1) is a no-op copy.
    """
    if factor >= 1.0 or factor <= 0:
        return img.copy()
    w, h = img.size
    small_w = max(1, int(round(w * factor)))
    small_h = max(1, int(round(h * factor)))
    small = img.resize((small_w, small_h), Image.BILINEAR)
    return small.resize((w, h), Image.BILINEAR)


def apply_cvd(img: Image.Image, cvd_type: CVDType, severity: float) -> Image.Image:
    """Simulate colour-vision deficiency with DaltonLens (Machado 2009)."""
    if severity <= 0 or cvd_type is None:
        return img.copy()
    deficiency = _CVD_MAP[CVDType(cvd_type)]
    src_mode = img.mode
    rgb = img.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    out = _CVD_SIM.simulate_cvd(arr, deficiency, severity=float(severity))
    out = np.clip(out, 0, 255).astype(np.uint8)
    result = Image.fromarray(out, mode="RGB")
    if src_mode != "RGB":
        result = result.convert(src_mode)
    return result


# ---------------------------------------------------------------------------
# Coordinate transform (actuation)
# ---------------------------------------------------------------------------
def jitter_coords(
    x: float,
    y: float,
    sigma_px: float,
    w: int,
    h: int,
    rng: np.random.Generator | None = None,
) -> tuple[int, int]:
    """Add gaussian noise to a click coordinate, clamped to ``[0, w) x [0, h)``."""
    if sigma_px <= 0:
        jx, jy = float(x), float(y)
    else:
        gen = rng if rng is not None else np.random.default_rng()
        jx = float(x) + float(gen.normal(0.0, sigma_px))
        jy = float(y) + float(gen.normal(0.0, sigma_px))
    cx = int(round(min(max(jx, 0.0), max(w - 1, 0))))
    cy = int(round(min(max(jy, 0.0), max(h - 1, 0))))
    return cx, cy


# ---------------------------------------------------------------------------
# High-level pipelines used by the persona agent
# ---------------------------------------------------------------------------
def perceive(png_bytes: bytes, persona: PersonaConfig) -> bytes:
    """Apply the persona's enabled perception perturbations, return PNG bytes.

    Order: downscale (acuity) -> blur (acuity) -> CVD (colour). Output PNG has
    the same dimensions as the input.
    """
    img = Image.open(io.BytesIO(png_bytes))
    img.load()
    original_size = img.size
    img = img.convert("RGB")

    if persona.downscale_factor and persona.downscale_factor < 1.0:
        img = downscale_in_place(img, persona.downscale_factor)
    if persona.blur_sigma and persona.blur_sigma > 0:
        img = blur(img, persona.blur_sigma)
    if persona.cvd_type is not None and persona.cvd_severity and persona.cvd_severity > 0:
        img = apply_cvd(img, persona.cvd_type, persona.cvd_severity)

    assert img.size == original_size, "perturbation changed image dimensions"
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def transport_downscale(png_bytes: bytes, max_w: int) -> tuple[bytes, float]:
    """Shrink the frame SENT to the model when wider than ``max_w`` (aspect kept).

    Returns ``(png_bytes, scale)`` where ``scale = sent_w / original_w`` (1.0 when
    no resize happened). UNLIKE the perception transforms above this intentionally
    changes dimensions: vision-token count scales with pixel area, so a smaller
    frame is materially faster/cheaper per Holo call. It is safe because the live
    API returns 0-1000 NORMALIZED coords which the client denormalizes against the
    image it was sent — the persona agent divides by ``scale`` to get back to true
    viewport pixels. (FakeHoloClient paths never downscale: viewports in tests are
    narrower than the default cap.)
    """
    img = Image.open(io.BytesIO(png_bytes))
    img.load()
    w, h = img.size
    if max_w <= 0 or w <= max_w:
        return png_bytes, 1.0
    scale = max_w / w
    small = img.convert("RGB").resize((max_w, max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    return buf.getvalue(), scale


def actuate(
    action: Action,
    persona: PersonaConfig,
    w: int,
    h: int,
    rng: np.random.Generator | None = None,
) -> Action:
    """Return a new Action with tremor jitter applied to its coords (if any).

    Coordinates are also clamped to the viewport regardless of tremor, so the
    runner always receives an in-bounds pixel.
    """
    if action.x is None or action.y is None:
        return action

    sigma = persona.tremor_sigma_px or 0.0
    cx, cy = jitter_coords(action.x, action.y, sigma, w, h, rng=rng)
    return action.model_copy(update={"x": cx, "y": cy})
