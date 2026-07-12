"""Offline benchmark A2 — Tremor (Gaussian coord noise) -> WCAG target-miss rate.

We drive the *real* actuation mechanism (`jitter_coords`, the same function the
persona agent uses for tremor) with a Monte-Carlo experiment and ask one question:

    If the model aims dead-centre at a square target of side S, how often does a
    tremor of magnitude sigma_px push the click OUTSIDE the target box?

That miss-rate is exactly the motor cost of the tremor perturbation, and we tie it
to the WCAG 2.5.5 Target Size thresholds: 44x44 CSS px (Level AA minimum) and
24x24 (Level AAA). Real personas carry tremor_sigma_px of grandma-72=4, impatient-
mobile=6, tremor=14; everyone else 0.

Reproducible: one np.random.default_rng(0) drives every draw. Pure offline (no
network, no browser). Run: `python -m benchmarks.b_a2_tremor_wcag`.
"""

from __future__ import annotations

import numpy as np

from benchmarks import common as c
from ghostpanel.engine.perturbation import jitter_coords

# --------------------------------------------------------------------------- grid
# Tremor magnitudes: the perturbation range spanning all real personas (0..14)
# plus a couple of severe points (20) to show the tail.
SIGMAS = [0, 2, 4, 6, 8, 10, 14, 20]
# Square target sizes in CSS px. 24 = WCAG AAA, 44 = WCAG AA minimum; the rest
# bracket typical real controls (icon buttons .. large CTAs).
SIZES = [24, 44, 64, 96, 160]

N = 20_000                 # Monte-Carlo trials per tremor magnitude
VIEWPORT = (1280, 800)     # true viewport the runner executes clicks in
# Aim point: viewport centre, far from any edge so clamping never distorts the
# miss statistics (a real button near an edge would only *reduce* effective size).
AIM_X, AIM_Y = VIEWPORT[0] // 2, VIEWPORT[1] // 2


def _land(sigma: float, rng: np.random.Generator) -> np.ndarray:
    """N jittered landing points (int px) for aiming at centre with `sigma` tremor.

    Uses the production jitter_coords so we measure the shipped mechanism, not a
    reimplementation. Returns an (N, 2) int array of (x, y) landings.
    """
    w, h = VIEWPORT
    pts = [jitter_coords(AIM_X, AIM_Y, sigma, w, h, rng=rng) for _ in range(N)]
    return np.asarray(pts, dtype=int)


def _miss_rate(landings: np.ndarray, size: int) -> float:
    """Fraction of landings falling OUTSIDE the centred square target of side `size`.

    A hit needs the point inside the box on BOTH axes (half-side = size/2).
    """
    half = size / 2.0
    inside = (np.abs(landings[:, 0] - AIM_X) <= half) & (
        np.abs(landings[:, 1] - AIM_Y) <= half
    )
    return float(1.0 - inside.mean())


def main() -> None:
    rng = np.random.default_rng(0)

    # For each tremor magnitude, draw one shared set of landings and evaluate
    # every target size against it (same tremor draws, different target => the
    # miss-rate curve is guaranteed monotonic in size, and mean radial error is
    # measured on the identical sample).
    landings_by_sigma: dict[int, np.ndarray] = {s: _land(s, rng) for s in SIGMAS}

    # miss-rate matrix: miss[sigma][size] as a percentage
    miss = {
        s: {sz: 100.0 * _miss_rate(landings_by_sigma[s], sz) for sz in SIZES}
        for s in SIGMAS
    }

    # mean radial error (px) per sigma = mean euclidean distance aim -> landing
    radial_err = {
        s: float(
            np.hypot(
                landings_by_sigma[s][:, 0] - AIM_X,
                landings_by_sigma[s][:, 1] - AIM_Y,
            ).mean()
        )
        for s in SIGMAS
    }

    # Sanity: sigma=0 is the identity (no jitter) -> exactly 0% miss everywhere.
    for sz in SIZES:
        assert miss[0][sz] == 0.0, f"sigma=0 must never miss (size={sz})"

    # -------------------------------------------------------------- headline numbers
    miss_44_at_14 = miss[14][44]   # WCAG AA target, tremor persona
    miss_44_at_4 = miss[4][44]     # WCAG AA target, grandma-72

    # Smallest target size keeping miss-rate < 5% at the tremor persona's sigma=14.
    # Fine sweep (not limited to the display grid) so the answer is a real threshold.
    tremor_landings = landings_by_sigma[14]
    min_safe_size_at_14 = next(
        (sz for sz in range(1, 401) if 100.0 * _miss_rate(tremor_landings, sz) < 5.0),
        None,
    )

    metrics = {
        "n_trials_per_cell": N,
        "viewport": list(VIEWPORT),
        "wcag_aa_min_px": 44,
        "wcag_aaa_min_px": 24,
        "miss_44px_at_sigma14_pct": round(miss_44_at_14, 1),
        "miss_44px_at_sigma4_pct": round(miss_44_at_4, 1),
        "miss_24px_at_sigma14_pct": round(miss[14][24], 1),
        "min_safe_size_at_sigma14_px": min_safe_size_at_14,
        "mean_radial_err_sigma14_px": round(radial_err[14], 2),
    }

    # Per-sigma rows for the miss-rate curve (44px = AA, 24px = AAA).
    table = [
        {
            "tremor_sigma_px": s,
            "miss_44px_pct": round(miss[s][44], 1),
            "miss_24px_pct": round(miss[s][24], 1),
            "mean_radial_err_px": round(radial_err[s], 2),
        }
        for s in SIGMAS
    ]

    headline = (
        f"A hand tremor (sigma=14px) misses a WCAG-minimum 44px target "
        f"{miss_44_at_14:.1f}% of the time; you need >={min_safe_size_at_14}px "
        f"targets to hold miss-rate under 5%."
    )

    notes = (
        "Model aims at target centre; jitter_coords (production tremor actuation) "
        "adds N(0,sigma) px on each axis, rounds and clamps. A miss = landing "
        "outside the square target box on either axis. Real personas: "
        "grandma-72 sigma=4, impatient-mobile sigma=6, tremor sigma=14; others 0. "
        "20k trials/sigma, shared across target sizes, seed=default_rng(0). "
        "sigma=0 verified as exact identity (0% miss)."
    )

    c.Result(
        id="a2_tremor_wcag",
        title="Tremor -> WCAG target-miss",
        kind="offline",
        headline=headline,
        metrics=metrics,
        table=table,
        notes=notes,
    ).write()

    # -------------------------------------------------------------- human summary
    print("Tremor -> WCAG target-miss  (aim at centre, 20k trials/sigma)")
    print(f"  viewport={VIEWPORT}  aim=({AIM_X},{AIM_Y})  seed=0")
    print()
    hdr = f"  {'sigma':>5} | {'radial_err':>10} | " + " | ".join(
        f"{sz:>3}px" for sz in SIZES
    )
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for s in SIGMAS:
        cells = " | ".join(f"{miss[s][sz]:5.1f}" for sz in SIZES)
        print(f"  {s:>5} | {radial_err[s]:9.2f}px | {cells}")
    print("  (matrix values are MISS-rate %, columns = target size)")
    print()
    print("  Headline numbers:")
    print(f"    44px @ sigma=14 (tremor)      : {miss_44_at_14:.1f}% miss")
    print(f"    44px @ sigma=4  (grandma-72)  : {miss_44_at_4:.1f}% miss")
    print(f"    24px @ sigma=14 (AAA target)  : {miss[14][24]:.1f}% miss")
    print(f"    smallest safe size @ sigma=14 : {min_safe_size_at_14}px (<5% miss)")
    print(f"    mean radial error @ sigma=14  : {radial_err[14]:.2f}px")
    print()
    print(f"  {headline}")


if __name__ == "__main__":
    main()
