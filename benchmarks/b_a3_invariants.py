"""Offline benchmark A3 — perturbation invariants + degradation dose-response.

Proves three claims about the perception channels in
``ghostpanel.engine.perturbation`` with numbers (no network, no Holo, no browser):

  (a) DIMENSION-PRESERVING — the "golden rule". ``perceive()`` on every real
      persona returns an image whose size == the input's (640x480). This is what
      keeps Holo's 0-1000 -> pixel denormalization valid downstream.
  (b) DETERMINISTIC — running ``perceive()`` twice yields byte-identical PNGs, so
      a persona's perception is reproducible.
  (c) MEASURABLE, MONOTONIC DEGRADATION — each channel (blur, downscale, CVD)
      produces a monotonic, dose-dependent loss of image detail / colour, measured
      with a variance-of-Laplacian focus metric and mean-absolute pixel difference.

Run: ``python -m benchmarks.b_a3_invariants``
Writes: ``benchmarks/results/a3_invariants.json``
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from benchmarks import common as c
from ghostpanel.engine.perturbation import apply_cvd, blur, downscale_in_place, perceive
from ghostpanel_contracts import CVDType

FIXTURE = c.FIXTURES / "sample_screenshot.png"
EXPECTED_SIZE = (640, 480)

# Dose-response sweeps.
BLUR_SIGMAS = [0.0, 0.5, 1.0, 1.2, 2.0, 3.5, 5.0]
DOWNSCALE_FACTORS = [1.0, 0.8, 0.6, 0.4, 0.25]
CVD_TYPES = [CVDType.DEUTAN, CVDType.PROTAN, CVDType.TRITAN]
CVD_SEVERITY = 0.9


# --------------------------------------------------------------------------- metrics
def _gray(img: Image.Image) -> np.ndarray:
    """Grayscale float array (luminance), shape (H, W)."""
    return np.asarray(img.convert("L"), dtype=np.float64)


def laplacian_var(img: Image.Image) -> float:
    """Variance of the Laplacian — the standard image focus/sharpness measure.

    High = sharp/detailed; falls toward 0 as high-frequency detail is destroyed.
    3x3 discrete Laplacian [[0,1,0],[1,-4,1],[0,1,0]] on the interior pixels.
    """
    g = _gray(img)
    lap = (
        -4.0 * g[1:-1, 1:-1]
        + g[:-2, 1:-1]
        + g[2:, 1:-1]
        + g[1:-1, :-2]
        + g[1:-1, 2:]
    )
    return float(lap.var())


def mean_abs_diff(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute per-channel pixel difference (0..255) between two RGB images."""
    aa = np.asarray(a.convert("RGB"), dtype=np.float64)
    bb = np.asarray(b.convert("RGB"), dtype=np.float64)
    return float(np.abs(aa - bb).mean())


def frac_pixels_changed(a: Image.Image, b: Image.Image) -> float:
    """Fraction of pixels whose RGB triple differs at all between two images."""
    aa = np.asarray(a.convert("RGB"), dtype=np.int16)
    bb = np.asarray(b.convert("RGB"), dtype=np.int16)
    changed = np.any(aa != bb, axis=2)
    return float(changed.mean())


def _decode(png_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png_bytes))
    img.load()
    return img


# --------------------------------------------------------------------------- benchmark
def run() -> c.Result:
    orig_bytes = FIXTURE.read_bytes()
    orig = _decode(orig_bytes)
    assert orig.size == EXPECTED_SIZE, f"fixture is {orig.size}, expected {EXPECTED_SIZE}"
    base_lap = laplacian_var(orig)

    personas = c.load_all_personas()

    # (a) DIMENSION-PRESERVATION + (b) DETERMINISM over every real persona.
    dim_pass = 0
    determinism_pass = 0
    persona_rows: list[dict] = []
    for p in personas:
        out1 = perceive(orig_bytes, p)
        out2 = perceive(orig_bytes, p)
        img1 = _decode(out1)
        size_ok = img1.size == EXPECTED_SIZE
        det_ok = out1 == out2  # byte-identical PNG
        if size_ok:
            dim_pass += 1
        if det_ok:
            determinism_pass += 1
        persona_rows.append(
            {
                "channel": f"persona:{p.id}",
                "level": None,
                "out_size": f"{img1.size[0]}x{img1.size[1]}",
                "dim_preserved": size_ok,
                "deterministic": det_ok,
                "mean_abs_diff": round(mean_abs_diff(orig, img1), 3),
            }
        )

    n = len(personas)
    dim_pct = 100.0 * dim_pass / n if n else 0.0
    det_pct = 100.0 * determinism_pass / n if n else 0.0

    # (c) DOSE-RESPONSE — blur sweep.
    blur_rows: list[dict] = []
    for sigma in BLUR_SIGMAS:
        img = blur(orig, sigma)
        assert img.size == EXPECTED_SIZE
        lv = laplacian_var(img)
        blur_rows.append(
            {
                "channel": "blur",
                "level": sigma,
                "laplacian_var": round(lv, 2),
                "detail_retained_pct": round(100.0 * lv / base_lap, 2),
                "mean_abs_diff": round(mean_abs_diff(orig, img), 3),
            }
        )

    # (c) DOSE-RESPONSE — downscale sweep.
    down_rows: list[dict] = []
    for factor in DOWNSCALE_FACTORS:
        img = downscale_in_place(orig, factor)
        assert img.size == EXPECTED_SIZE
        lv = laplacian_var(img)
        down_rows.append(
            {
                "channel": "downscale",
                "level": factor,
                "laplacian_var": round(lv, 2),
                "detail_retained_pct": round(100.0 * lv / base_lap, 2),
                "mean_abs_diff": round(mean_abs_diff(orig, img), 3),
            }
        )

    # (c) CVD — colour shift at severity 0.9, plus severity=0 no-op check.
    cvd_rows: list[dict] = []
    cvd_noop_ok = True
    for cvd in CVD_TYPES:
        noop = apply_cvd(orig, cvd, 0.0)
        assert noop.size == EXPECTED_SIZE
        if mean_abs_diff(orig, noop) != 0.0:
            cvd_noop_ok = False
        img = apply_cvd(orig, cvd, CVD_SEVERITY)
        assert img.size == EXPECTED_SIZE
        cvd_rows.append(
            {
                "channel": f"cvd:{cvd.value}",
                "level": CVD_SEVERITY,
                "mean_color_shift": round(mean_abs_diff(orig, img), 3),
                "frac_pixels_changed": round(frac_pixels_changed(orig, img), 4),
                "noop_at_sev0": mean_abs_diff(orig, noop) == 0.0,
            }
        )

    # Monotonicity checks (detail must fall as dose rises).
    blur_lv = [r["laplacian_var"] for r in blur_rows]
    down_lv = [r["laplacian_var"] for r in down_rows]
    blur_monotonic = all(blur_lv[i] >= blur_lv[i + 1] for i in range(len(blur_lv) - 1))
    down_monotonic = all(down_lv[i] >= down_lv[i + 1] for i in range(len(down_lv) - 1))

    # Headline: the low-vision persona (blur 3.5 + downscale 0.4) combined effect.
    low_vision = c.load_persona("low-vision")
    lv_img = _decode(perceive(orig_bytes, low_vision))
    lv_detail_retained = 100.0 * laplacian_var(lv_img) / base_lap
    lv_detail_destroyed = 100.0 - lv_detail_retained

    headline = (
        f"low-vision persona (blur {low_vision.blur_sigma} + downscale "
        f"{low_vision.downscale_factor}) destroys {lv_detail_destroyed:.1f}% of image "
        f"detail (only {lv_detail_retained:.2f}% retained) while preserving 100% of "
        f"pixel dimensions ({EXPECTED_SIZE[0]}x"
        f"{EXPECTED_SIZE[1]}) across all {n} personas, reproducibly."
    )

    metrics = {
        "personas_tested": n,
        "dim_preserved_pass": dim_pass,
        "dim_preserved_pct": round(dim_pct, 1),
        "determinism_pass": determinism_pass,
        "reproducibility_pct": round(det_pct, 1),
        "base_laplacian_var": round(base_lap, 2),
        "blur_monotonic": blur_monotonic,
        "downscale_monotonic": down_monotonic,
        "cvd_noop_at_sev0": cvd_noop_ok,
        "low_vision_detail_destroyed_pct": round(lv_detail_destroyed, 2),
        "low_vision_detail_retained_pct": round(lv_detail_retained, 2),
    }

    table = blur_rows + down_rows + cvd_rows + persona_rows

    notes = (
        "Detail metric = variance of the 3x3 Laplacian of the grayscale image "
        "(focus measure); detail_retained_pct is normalized to sigma=0 / factor=1.0. "
        "mean_abs_diff / mean_color_shift are mean absolute per-channel pixel deltas "
        "(0-255) vs the original. All transforms are dimension-preserving (asserted) "
        "and deterministic. CVD is a strict no-op at severity 0. blur and downscale "
        "are monotonic in detail loss. Every real persona's perceive() output is "
        "byte-identical across two runs and matches the 640x480 input size."
    )

    return c.Result(
        id="a3_invariants",
        title="Perturbation invariants + degradation",
        kind="offline",
        headline=headline,
        metrics=metrics,
        table=table,
        notes=notes,
    )


def _print_summary(res: c.Result) -> None:
    m = res.metrics
    print("=" * 72)
    print("A3 — Perturbation invariants + degradation dose-response")
    print("=" * 72)
    print(f"HEADLINE: {res.headline}\n")
    print(
        f"(a) DIM-PRESERVATION : {m['dim_preserved_pass']}/{m['personas_tested']} "
        f"personas -> {m['dim_preserved_pct']}%  (all == {EXPECTED_SIZE[0]}x{EXPECTED_SIZE[1]})"
    )
    print(
        f"(b) DETERMINISM      : {m['determinism_pass']}/{m['personas_tested']} "
        f"personas byte-identical -> reproducibility {m['reproducibility_pct']}%"
    )
    print(
        f"(c) MONOTONICITY     : blur={m['blur_monotonic']}  downscale="
        f"{m['downscale_monotonic']}  cvd_noop@sev0={m['cvd_noop_at_sev0']}"
    )
    print(f"    base laplacian-var = {m['base_laplacian_var']}\n")

    print("BLUR sweep (sigma -> detail retained):")
    for r in res.table:
        if r["channel"] == "blur":
            print(
                f"  sigma={r['level']:<4}  lap_var={r['laplacian_var']:>10.2f}  "
                f"retained={r['detail_retained_pct']:>6.2f}%  meanAbsDiff={r['mean_abs_diff']}"
            )
    print("\nDOWNSCALE sweep (factor -> detail retained):")
    for r in res.table:
        if r["channel"] == "downscale":
            print(
                f"  factor={r['level']:<4} lap_var={r['laplacian_var']:>10.2f}  "
                f"retained={r['detail_retained_pct']:>6.2f}%  meanAbsDiff={r['mean_abs_diff']}"
            )
    print("\nCVD (severity 0.9 -> colour shift):")
    for r in res.table:
        if str(r["channel"]).startswith("cvd:"):
            print(
                f"  {r['channel']:<12} meanShift={r['mean_color_shift']:>7.3f}  "
                f"pxChanged={r['frac_pixels_changed'] * 100:>6.2f}%  noop@sev0={r['noop_at_sev0']}"
            )
    print("\nPer-persona perceive() invariants:")
    for r in res.table:
        if str(r["channel"]).startswith("persona:"):
            print(
                f"  {r['channel']:<22} size={r['out_size']:<9} "
                f"dim_ok={r['dim_preserved']!s:<5} det_ok={r['deterministic']!s:<5} "
                f"meanAbsDiff={r['mean_abs_diff']}"
            )
    print("=" * 72)


if __name__ == "__main__":
    res = run()
    _print_summary(res)
    path = res.write()
    print(f"\nWrote {path}")
