"""Offline accuracy benchmark for Ghostpanel's outcome classifiers.

The survival curve, the abandonment heatmap and the success count are only as
trustworthy as the three tiny classifiers that feed them:

  * `is_stuck`       — did the persona rage-quit? (no-progress loop detector)
  * `frames_similar` — are two consecutive screenshots the same screen?
  * `is_success`     — did the persona actually complete the task?

If `is_stuck` false-fires we invent rage-quits that never happened; if it
misses we never record the abandonment pixel. If `frames_similar` is wrong we
mis-annotate dud actions, which in turn poisons `is_stuck`'s path-2. So we
measure precision / recall of these mechanisms on synthetic *labeled* traces.

Nothing here touches the live Holo API, Playwright or the network — it is a
pure offline unit-accuracy study over datasets we generate and label ourselves.

Run:  python -m benchmarks.b_d1_classifiers
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

import numpy as np

from benchmarks import common as c
from ghostpanel.runner.detect import (
    NO_CHANGE_NOTE,
    frames_similar,
    is_stuck,
    is_success,
)

SEED = 0


# --------------------------------------------------------------------------- helpers
def click_caption(x: int, y: int, dud: bool = False) -> str:
    """A runner-style click caption that matches detect._CLICK_CAPTION_RE.

    `dud=True` appends the NO_CHANGE_NOTE annotation the session loop adds when
    the following frame was visually identical (what path-2 of is_stuck keys on).
    """
    cap = f"clicking at ({x}, {y})"
    return cap + NO_CHANGE_NOTE if dud else cap


@dataclass
class PRResult:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


# --------------------------------------------------------------------------- stuck dataset
INTENTS = [
    "Clicking Sign up",
    "Typing email address",
    "Scrolling down",
    "Clicking Continue",
    "Dismissing cookie banner",
    "Clicking Create account",
    "Selecting country",
    "Clicking Next",
]


def build_stuck_dataset(rng: np.random.Generator):
    """Return list of (history, label, subtype). label=True => genuinely stuck."""
    ds: list[tuple[list[str], bool, str]] = []

    # ---- POSITIVE: exact-repeat of the last `window` core captions -------------
    for _ in range(50):
        intent = INTENTS[rng.integers(len(INTENTS))]
        # optional progressing prefix (only the last 3 matter)
        prefix_n = int(rng.integers(0, 4))
        prefix = [INTENTS[rng.integers(len(INTENTS))] for _ in range(prefix_n)]
        # some repeats carry a stray annotation on the tail entries; cores still match
        tail = [intent, intent, intent]
        if rng.random() < 0.4:
            tail = [intent, intent + NO_CHANGE_NOTE, intent + NO_CHANGE_NOTE]
        ds.append((prefix + tail, True, "exact_repeat"))

    # ---- POSITIVE: jittered clicks on a dead spot, >=2 marked no-change --------
    for _ in range(50):
        x0 = int(rng.integers(50, 1200))
        y0 = int(rng.integers(50, 750))
        pts = [(x0, y0)]
        for _ in range(2):
            dx = int(rng.integers(-14, 15))  # inclusive of +/-14
            dy = int(rng.integers(-14, 15))
            pts.append((x0 + dx, y0 + dy))
        # exactly 2 or 3 duds (>= window-1 == 2 required); first may be a dud too
        dud_count = int(rng.integers(2, 4))
        dud_flags = [False, False, False]
        for i in rng.choice(3, size=dud_count, replace=False):
            dud_flags[i] = True
        hist = [click_caption(x, y, dud=f) for (x, y), f in zip(pts, dud_flags)]
        # ensure cores are NOT all identical so we truly exercise path-2, not path-1
        if len({click_caption(x, y) for x, y in pts}) == 1:
            pts[1] = (x0 + 1, y0)  # nudge so caption text differs
            hist[1] = click_caption(*pts[1], dud=dud_flags[1])
        ds.append((hist, True, "dead_spot_clicks"))

    # ---- NEGATIVE: genuine progress, all-distinct intents ---------------------
    for _ in range(45):
        n = int(rng.integers(3, 7))
        idx = rng.choice(len(INTENTS), size=min(n, len(INTENTS)), replace=False)
        hist = [INTENTS[i] for i in idx]
        ds.append((hist, False, "distinct_progress"))

    # ---- NEGATIVE: clicks that MOVE (>14px on an axis) => real navigation ------
    for _ in range(35):
        x0 = int(rng.integers(50, 1000))
        y0 = int(rng.integers(50, 600))
        pts = [(x0, y0)]
        for _ in range(2):
            # force a move beyond the radius on at least one axis
            dx = int(rng.integers(15, 120)) * (1 if rng.random() < 0.5 else -1)
            dy = int(rng.integers(15, 120)) * (1 if rng.random() < 0.5 else -1)
            pts.append((x0 + dx, y0 + dy))
        # even mark them dud — moving clicks must NOT count as stuck
        hist = [click_caption(x, y, dud=True) for x, y in pts]
        ds.append((hist, False, "moving_clicks"))

    # ---- NEGATIVE: close clicks but NOT annotated no-change (screen reacted) ---
    for _ in range(25):
        x0 = int(rng.integers(50, 1200))
        y0 = int(rng.integers(50, 750))
        pts = [
            (x0, y0),
            (x0 + int(rng.integers(-14, 15)), y0 + int(rng.integers(-14, 15))),
            (x0 + int(rng.integers(-14, 15)), y0 + int(rng.integers(-14, 15))),
        ]
        # 0 or 1 duds only (< window-1) => not stuck, the clicks did something
        dud_flags = [False, False, False]
        if rng.random() < 0.5:
            dud_flags[int(rng.integers(3))] = True
        hist = [click_caption(x, y, dud=f) for (x, y), f in zip(pts, dud_flags)]
        ds.append((hist, False, "close_but_reacted"))

    # ---- NEGATIVE: fewer than `window` steps => cannot be stuck yet ------------
    for _ in range(20):
        n = int(rng.integers(0, 3))  # 0,1,2 entries
        hist = [INTENTS[rng.integers(len(INTENTS))] for _ in range(n)]
        ds.append((hist, False, "too_short"))

    rng.shuffle(ds)  # type: ignore[arg-type]
    return ds


def eval_stuck(ds) -> tuple[PRResult, dict[str, PRResult]]:
    overall = PRResult(0, 0, 0, 0)
    by_sub: dict[str, PRResult] = {}
    for hist, label, sub in ds:
        pred = is_stuck(hist)
        r = by_sub.setdefault(sub, PRResult(0, 0, 0, 0))
        for tgt in (overall, r):
            if label and pred:
                tgt.tp += 1
            elif label and not pred:
                tgt.fn += 1
            elif not label and pred:
                tgt.fp += 1
            else:
                tgt.tn += 1
    return overall, by_sub


# --------------------------------------------------------------------------- frames dataset
def _png(arr: np.ndarray) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8), mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _base_image(rng: np.random.Generator, w: int = 240, h: int = 160) -> np.ndarray:
    """A structured grayscale image (gradient + a few blocks) — like a real UI."""
    yy, xx = np.mgrid[0:h, 0:w]
    img = (xx / w * 180 + yy / h * 40).astype(np.float64)
    for _ in range(4):
        x0 = int(rng.integers(0, w - 40))
        y0 = int(rng.integers(0, h - 30))
        img[y0 : y0 + 30, x0 : x0 + 40] = float(rng.integers(0, 256))
    return np.clip(img, 0, 255)


def build_frames_dataset(rng: np.random.Generator):
    """Return list of (png_a, png_b, label) where label=True => should be similar."""
    ds: list[tuple[bytes, bytes, bool]] = []

    # identical bytes -> similar
    for _ in range(40):
        img = _base_image(rng)
        b = _png(img)
        ds.append((b, b, True))

    # tiny-noise variants (small enough to survive the 96px-mean threshold) -> similar
    for _ in range(40):
        img = _base_image(rng)
        noise = rng.normal(0, 3.0, size=img.shape)  # sigma=3 grayscale levels
        a = _png(img)
        b = _png(np.clip(img + noise, 0, 255))
        ds.append((a, b, True))

    # clearly different content -> not similar
    for _ in range(40):
        img = _base_image(rng)
        other = _base_image(rng)  # independent layout/blocks
        # guarantee a large difference
        other = np.clip(other + 60, 0, 255)
        ds.append((_png(img), _png(other), False))

    rng.shuffle(ds)  # type: ignore[arg-type]
    return ds


def eval_frames(ds) -> tuple[float, PRResult]:
    r = PRResult(0, 0, 0, 0)
    for a, b, label in ds:
        pred = frames_similar(a, b)
        if label and pred:
            r.tp += 1
        elif label and not pred:
            r.fn += 1
        elif not label and pred:
            r.fp += 1
        else:
            r.tn += 1
    acc = (r.tp + r.tn) / max(1, r.tp + r.tn + r.fp + r.fn)
    return acc, r


def sweep_noise(rng: np.random.Generator):
    """Find the noise sigma where frames_similar flips similar->different."""
    rows = []
    sigmas = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 40.0]
    trials = 30
    for s in sigmas:
        sim = 0
        for _ in range(trials):
            img = _base_image(rng)
            noise = rng.normal(0, s, size=img.shape)
            if frames_similar(_png(img), _png(np.clip(img + noise, 0, 255))):
                sim += 1
        rows.append({"noise_sigma": s, "frac_similar": round(sim / trials, 3)})
    return rows


# --------------------------------------------------------------------------- is_success
class _FakePage:
    """Stand-in for a Playwright page; is_success default path never touches it."""


def check_is_success() -> tuple[bool, list[dict]]:
    async def run():
        page = _FakePage()
        checks = []

        async def _apred(_):  # async predicate
            return True

        def _raiser(_):
            raise RuntimeError("boom")

        checks.append(("predicate_true", await is_success(page, lambda _p: True), True))
        checks.append(("predicate_false", await is_success(page, lambda _p: False), False))
        checks.append(("predicate_async_true", await is_success(page, _apred), True))
        checks.append(("predicate_raises->false", await is_success(page, _raiser), False))
        # default (no predicate): conservative, always False -> anti-false-positive
        checks.append(("default_no_predicate", await is_success(page), False))
        checks.append(("default_none_page", await is_success(None), False))
        return checks

    checks = asyncio.run(run())
    rows = [
        {"check": name, "got": got, "expected": exp, "pass": got == exp}
        for name, got, exp in checks
    ]
    return all(r["pass"] for r in rows), rows


# --------------------------------------------------------------------------- main
def main() -> None:
    rng = np.random.default_rng(SEED)

    # sanity: show a couple synthetic captions parse the way path-2 expects
    from ghostpanel.runner.detect import _CLICK_CAPTION_RE, _core_caption

    samples = [click_caption(960, 312), click_caption(500, 300, dud=True)]
    print("caption parse check:")
    for s in samples:
        m = _CLICK_CAPTION_RE.match(_core_caption(s))
        print(f"  {s!r:60s} -> core={_core_caption(s)!r} match={m.groups() if m else None}")

    # 1) is_stuck ------------------------------------------------------------
    stuck_ds = build_stuck_dataset(rng)
    stuck, stuck_by_sub = eval_stuck(stuck_ds)
    n_neg = sum(1 for _, lbl, _ in stuck_ds if not lbl)

    # 2) frames_similar ------------------------------------------------------
    frames_ds = build_frames_dataset(rng)
    frames_acc, frames_pr = eval_frames(frames_ds)
    noise_rows = sweep_noise(rng)

    # 3) is_success ----------------------------------------------------------
    success_ok, success_rows = check_is_success()

    # ---- assemble tables ---------------------------------------------------
    confusion_table = [
        {
            "classifier": "is_stuck",
            "TP": stuck.tp, "FP": stuck.fp, "FN": stuck.fn, "TN": stuck.tn,
            "precision": round(stuck.precision, 4),
            "recall": round(stuck.recall, 4),
            "f1": round(stuck.f1, 4),
        },
        {
            "classifier": "frames_similar",
            "TP": frames_pr.tp, "FP": frames_pr.fp,
            "FN": frames_pr.fn, "TN": frames_pr.tn,
            "precision": round(frames_pr.precision, 4),
            "recall": round(frames_pr.recall, 4),
            "f1": round(frames_pr.f1, 4),
        },
    ]
    subtype_table = [
        {
            "subtype": sub,
            "n": r.tp + r.fp + r.fn + r.tn,
            "fired": r.tp + r.fp,
            "TP": r.tp, "FP": r.fp, "FN": r.fn, "TN": r.tn,
        }
        for sub, r in sorted(stuck_by_sub.items())
    ]

    headline = (
        f"Stuck-detector: precision {stuck.precision*100:.0f}%, "
        f"recall {stuck.recall*100:.0f}%, "
        f"{stuck.fp} false rage-quits on {n_neg} progressing traces; "
        f"frames-similar accuracy {frames_acc*100:.0f}%; "
        f"is_success {'all checks pass' if success_ok else 'FAILED'}."
    )

    notes = (
        f"Offline, seeded (np.random.default_rng({SEED})). "
        f"is_stuck over {len(stuck_ds)} labeled histories "
        f"(positives: exact-repeat loops + jittered dead-spot clicks w/ "
        f"'{NO_CHANGE_NOTE.strip()}'; negatives: distinct progress, moving clicks "
        f"(>14px), close-but-reacted clicks, <3-step histories). "
        f"frames_similar over {len(frames_ds)} labeled PNG pairs "
        f"(identical bytes, sigma=3 noise variants, distinct content). "
        f"Noise sweep locates the similar->different flip. "
        f"is_success: predicate True/False/async/raises propagate correctly and "
        f"the default (no predicate) is always-False (anti-false-positive)."
    )

    res = c.Result(
        id="d1_classifiers",
        title="Outcome-classifier accuracy",
        kind="offline",
        headline=headline,
        metrics={
            "stuck_precision": round(stuck.precision, 4),
            "stuck_recall": round(stuck.recall, 4),
            "stuck_f1": round(stuck.f1, 4),
            "frames_similar_acc": round(frames_acc, 4),
            "stuck_false_quits": stuck.fp,
            "stuck_n": len(stuck_ds),
            "stuck_negatives": n_neg,
            "frames_n": len(frames_ds),
            "is_success_ok": success_ok,
        },
        table=confusion_table + subtype_table,
        notes=notes,
    )
    path = res.write()

    # ---- console summary ---------------------------------------------------
    print("\n=== is_stuck ===")
    print(f"  precision={stuck.precision:.3f} recall={stuck.recall:.3f} "
          f"f1={stuck.f1:.3f}")
    print(f"  confusion: TP={stuck.tp} FP={stuck.fp} FN={stuck.fn} TN={stuck.tn}")
    print(f"  false rage-quits (FP) on {n_neg} progressing traces: {stuck.fp}")
    for row in subtype_table:
        print(f"    {row['subtype']:20s} n={row['n']:3d} fired={row['fired']:3d} "
              f"(TP={row['TP']} FP={row['FP']} FN={row['FN']} TN={row['TN']})")

    print("\n=== frames_similar ===")
    print(f"  accuracy={frames_acc:.3f}  "
          f"TP={frames_pr.tp} FP={frames_pr.fp} FN={frames_pr.fn} TN={frames_pr.tn}")
    print("  noise sweep (sigma -> frac judged similar):")
    for row in noise_rows:
        print(f"    sigma={row['noise_sigma']:>5} -> {row['frac_similar']}")

    print("\n=== is_success ===")
    for row in success_rows:
        print(f"  {'PASS' if row['pass'] else 'FAIL'}  {row['check']:26s} "
              f"got={row['got']} expected={row['expected']}")
    print(f"  overall: {'PASS' if success_ok else 'FAIL'}")

    print(f"\nHEADLINE: {headline}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
