"""Benchmark C3 — perturbation compute overhead (offline).

Question: how many milliseconds does it cost to mechanically degrade one
screenshot before we hand it to Holo? We time the full ``perceive()`` pipeline
(PNG decode -> downscale -> blur -> CVD -> PNG encode) per real persona, plus
each transform in isolation on an already-decoded PIL image.

Point of the number: perturbation is essentially free next to the ~seconds of a
single Holo inference call, so mechanical fidelity costs nothing at runtime.

Run:  python -m benchmarks.b_c3_overhead
"""

from __future__ import annotations

import io
import time
from typing import Callable

from PIL import Image

from benchmarks import common as c
from ghostpanel.engine.perturbation import apply_cvd, blur, downscale_in_place, perceive
from ghostpanel_contracts import CVDType, PersonaConfig

# --- knobs ------------------------------------------------------------------
WARMUP = 10
ITERS = 80
# Isolated-transform params (match the "full pipeline" persona below so the
# decomposition is apples-to-apples).
BLUR_SIGMA = 3.5
DOWNSCALE_FACTOR = 0.4
CVD_TYPE = CVDType.DEUTAN
CVD_SEVERITY = 0.9
# Reference cost of one Holo inference call. Estimate — to be confirmed by the
# live latency benchmark.
REFERENCE_INFERENCE_MS = 2000.0
FULLSIZE = (1280, 800)  # true runtime screenshot size


def _bench(fn: Callable[[], object], iters: int = ITERS, warmup: int = WARMUP):
    """Return (median_ms, p95_ms) for ``fn`` using perf_counter."""
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return c.percentile(samples, 50), c.percentile(samples, 95)


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _full_pipeline_persona() -> PersonaConfig:
    """Synthetic worst case: every perception channel on at once."""
    return PersonaConfig(
        id="full-pipeline",
        name="Full pipeline (all channels)",
        blurb="Synthetic: downscale + blur + CVD together — heaviest perceive().",
        blur_sigma=BLUR_SIGMA,
        downscale_factor=DOWNSCALE_FACTOR,
        cvd_type=CVD_TYPE,
        cvd_severity=CVD_SEVERITY,
    )


def run() -> c.Result:
    fixture_png = (c.FIXTURES / "sample_screenshot.png").read_bytes()
    fixture_img = Image.open(io.BytesIO(fixture_png)).convert("RGB")
    fixture_px = f"{fixture_img.size[0]}x{fixture_img.size[1]}"

    # Realistic full-size screenshot: upscale the fixture to 1280x800.
    full_img = fixture_img.resize(FULLSIZE, Image.BILINEAR)
    full_png = _png_bytes(full_img)
    fullsize_px = f"{FULLSIZE[0]}x{FULLSIZE[1]}"

    personas = c.load_all_personas()
    table: list[dict] = []

    # 1) Full perceive() per real persona at the fixture size (640x480).
    for p in personas:
        med, p95 = _bench(lambda p=p: perceive(fixture_png, p))
        table.append(
            {"persona": p.id, "resolution": fixture_px,
             "perceive_ms_median": round(med, 3), "perceive_ms_p95": round(p95, 3)}
        )

    # 3) Full perceive() per real persona at the realistic runtime size (1280x800).
    full_medians: list[float] = []
    for p in personas:
        med, p95 = _bench(lambda p=p: perceive(full_png, p))
        full_medians.append(med)
        table.append(
            {"persona": p.id, "resolution": fullsize_px,
             "perceive_ms_median": round(med, 3), "perceive_ms_p95": round(p95, 3)}
        )

    # Full-pipeline (all channels) worst case at runtime size — headline number.
    fp_persona = _full_pipeline_persona()
    fp_med, fp_p95 = _bench(lambda: perceive(full_png, fp_persona))
    table.append(
        {"persona": fp_persona.id, "resolution": fullsize_px,
         "perceive_ms_median": round(fp_med, 3), "perceive_ms_p95": round(fp_p95, 3)}
    )

    # 2) Isolated transform cost on an already-decoded PIL image at runtime size
    #    (excludes PNG decode/encode so each channel's transform cost stands alone).
    channels: dict[str, Callable[[], object]] = {
        f"blur (σ={BLUR_SIGMA})": lambda: blur(full_img, BLUR_SIGMA),
        f"downscale (×{DOWNSCALE_FACTOR})": lambda: downscale_in_place(full_img, DOWNSCALE_FACTOR),
        f"cvd ({CVD_TYPE.value},{CVD_SEVERITY})": lambda: apply_cvd(full_img, CVD_TYPE, CVD_SEVERITY),
    }
    channel_meds: dict[str, float] = {}
    for label, fn in channels.items():
        med, p95 = _bench(fn)
        channel_meds[label] = med
        table.append(
            {"persona": f"[channel] {label}", "resolution": fullsize_px,
             "perceive_ms_median": round(med, 3), "perceive_ms_p95": round(p95, 3)}
        )

    pct_of_inference = fp_med / REFERENCE_INFERENCE_MS * 100.0
    median_full = c.percentile(full_medians, 50)

    headline = (
        f"Full perception perturbation adds a median of {fp_med:.1f} ms/frame at "
        f"{fullsize_px} — under {pct_of_inference:.2f}% of a single ~{REFERENCE_INFERENCE_MS/1000:.0f}s "
        f"Holo inference call."
    )

    metrics = {
        "fixture_px": fixture_px,
        "fullsize_px": fullsize_px,
        "iters": ITERS,
        "warmup": WARMUP,
        "reference_inference_ms": REFERENCE_INFERENCE_MS,
        "full_pipeline_ms_median": round(fp_med, 3),
        "full_pipeline_ms_p95": round(fp_p95, 3),
        "full_pipeline_pct_of_inference": round(pct_of_inference, 4),
        "real_personas_ms_median_1280x800": round(median_full, 3),
        "blur_ms_median": round(channel_meds[f"blur (σ={BLUR_SIGMA})"], 3),
        "downscale_ms_median": round(channel_meds[f"downscale (×{DOWNSCALE_FACTOR})"], 3),
        "cvd_ms_median": round(channel_meds[f"cvd ({CVD_TYPE.value},{CVD_SEVERITY})"], 3),
    }

    notes = (
        "perf_counter timing; median + p95 over "
        f"{ITERS} iterations after {WARMUP} warmup runs. Timings are "
        "machine-dependent. Isolated channels run on an already-decoded PIL image "
        "(PNG decode+encode excluded) at the runtime size so each transform's cost "
        "stands alone; full perceive() includes PNG decode+encode. The "
        f"{REFERENCE_INFERENCE_MS/1000:.0f}s inference reference is an estimate to be "
        "confirmed by the live latency benchmark. The full-pipeline persona is a "
        "synthetic worst case with all three perception channels enabled at once."
    )

    return c.Result(
        id="c3_overhead",
        title="Perturbation compute overhead",
        kind="offline",
        headline=headline,
        metrics=metrics,
        table=table,
        notes=notes,
    )


if __name__ == "__main__":
    result = run()
    path = result.write()

    print(result.headline)
    print()
    m = result.metrics
    print(f"Full pipeline @ {m['fullsize_px']}: "
          f"median {m['full_pipeline_ms_median']} ms, p95 {m['full_pipeline_ms_p95']} ms "
          f"({m['full_pipeline_pct_of_inference']}% of a {int(m['reference_inference_ms'])} ms inference)")
    print(f"Real personas @ {m['fullsize_px']}: median {m['real_personas_ms_median_1280x800']} ms")
    print(f"Isolated channels @ {m['fullsize_px']} (transform only): "
          f"blur {m['blur_ms_median']} ms | downscale {m['downscale_ms_median']} ms | "
          f"cvd {m['cvd_ms_median']} ms")
    print()
    print(f"{'row':<28}{'resolution':>12}{'median ms':>12}{'p95 ms':>10}")
    for r in result.table:
        print(f"{r['persona']:<28}{r['resolution']:>12}{r['perceive_ms_median']:>12}{r['perceive_ms_p95']:>10}")
    print()
    print(f"wrote {path}")
