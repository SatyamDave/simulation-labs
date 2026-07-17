"""Grounding eval harness — the gate that must pass before any model swap ships.

Ghostpanel's whole value proposition rests on ONE model skill: given a screenshot
and an instruction, put the click on the right pixel. If we swap the inference
backend (hosted Holo -> self-hosted vLLM -> a different model entirely) we MUST
re-measure that skill before trusting the new backend in production. This module
is that measurement.

It scores ANY ``HoloClient`` implementation on click-localization accuracy against
a set of ``GroundingCase`` (screenshot, instruction, expected_pixel, tolerance)
and reports a single number: **click accuracy = % of cases whose predicted click
landed within tolerance of the target**.

Two ways to run it:

  * **Offline / CI smoke test** — ``tests/engine/test_grounding_eval.py`` runs the
    harness against a ``FakeHoloClient`` scripted to hit the targets, proving the
    plumbing (image sizing, distance math, scoring) is correct with no network.

  * **Live gate** — run this file as a script against a real or self-hosted
    endpoint::

        # hosted vendor
        HAI_API_KEY=sk-... python -m tests.engine.grounding_eval

        # self-hosted vLLM (see docs/SELF_HOSTING.md)
        GROUNDING_EVAL_BACKEND=selfhost \\
        HAI_BASE_URL=http://localhost:8000/v1 \\
        HAI_MODEL=Hcompany/Holo-3.1-35B-A3B \\
        python -m tests.engine.grounding_eval

    It prints per-case results and the overall accuracy, and exits non-zero if the
    score is below ``--min-accuracy`` (default 0.5) so it can be a CI gate.

The synthetic cases are constructed deterministically with Pillow (a single bright
button on a plain background) so the target pixel is known exactly and the eval is
reproducible on any machine. One real-world case is seeded from
``fixtures/sample_screenshot.png``.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

# Repo layout: tests/engine/grounding_eval.py -> parents[2] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "fixtures" / "sample_screenshot.png"


# ---------------------------------------------------------------------------
# Case + result models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GroundingCase:
    """One click-localization test.

    ``image_png`` is the exact screenshot handed to the client. ``expected`` is
    the ground-truth pixel the click should land on. ``tolerance_px`` is the
    Euclidean radius (in pixels) within which a prediction counts as correct.
    """

    name: str
    image_png: bytes
    instruction: str
    expected: tuple[int, int]
    tolerance_px: float = 40.0


@dataclass
class CaseResult:
    name: str
    instruction: str
    expected: tuple[int, int]
    predicted: tuple[int, int]
    distance: float
    tolerance_px: float
    passed: bool
    error: str = ""


@dataclass
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def accuracy(self) -> float:
        """Click accuracy: fraction of cases within tolerance (0.0-1.0)."""
        return self.passed / self.total if self.total else 0.0

    @property
    def mean_distance(self) -> float:
        scored = [r for r in self.results if not r.error]
        return sum(r.distance for r in scored) / len(scored) if scored else float("nan")

    def format(self) -> str:
        lines = ["Grounding eval — click localization", "=" * 48]
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            if r.error:
                lines.append(f"[{mark}] {r.name}: ERROR {r.error}")
            else:
                lines.append(
                    f"[{mark}] {r.name}: expected {r.expected} got {r.predicted} "
                    f"dist={r.distance:.1f}px (tol {r.tolerance_px:.0f}px)"
                )
        lines.append("-" * 48)
        lines.append(
            f"accuracy = {self.accuracy * 100:.1f}%  ({self.passed}/{self.total})  "
            f"mean_distance = {self.mean_distance:.1f}px"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic synthetic case construction
# ---------------------------------------------------------------------------
def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_button_case(
    name: str,
    instruction: str,
    *,
    size: tuple[int, int] = (640, 480),
    button_xywh: tuple[int, int, int, int] = (220, 200, 200, 60),
    tolerance_px: float = 40.0,
    button_color: tuple[int, int, int] = (30, 120, 220),
) -> GroundingCase:
    """Build a deterministic case: a single filled button on a plain canvas.

    The ground-truth ``expected`` pixel is the exact centre of the drawn button,
    so the case is fully reproducible with no external assets.
    """
    w, h = size
    bx, by, bw, bh = button_xywh
    img = Image.new("RGB", (w, h), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([bx, by, bx + bw, by + bh], fill=button_color)
    center = (bx + bw // 2, by + bh // 2)
    return GroundingCase(
        name=name,
        image_png=_png_bytes(img),
        instruction=instruction,
        expected=center,
        tolerance_px=tolerance_px,
    )


def default_cases() -> list[GroundingCase]:
    """The seed suite: two deterministic synthetic buttons + the repo fixture.

    The fixture case's ``expected`` target is the image centre with a generous
    tolerance — it exists so the harness exercises a real screenshot end to end;
    tighten its target once a canonical element in the fixture is agreed on.
    """
    cases = [
        make_button_case(
            "synthetic_center_button",
            "Click the blue Sign up button",
            button_xywh=(220, 200, 200, 60),
        ),
        make_button_case(
            "synthetic_topright_button",
            "Click the blue button in the top-right",
            size=(800, 600),
            button_xywh=(600, 40, 150, 50),
        ),
    ]
    if _FIXTURE.is_file():
        png = _FIXTURE.read_bytes()
        with Image.open(io.BytesIO(png)) as im:
            w, h = im.size
        cases.append(
            GroundingCase(
                name="fixture_sample_screenshot",
                image_png=png,
                instruction="Click the primary button",
                expected=(w // 2, h // 2),
                tolerance_px=max(w, h),  # lenient: presence check, not a tight target
            )
        )
    return cases


# ---------------------------------------------------------------------------
# The eval itself
# ---------------------------------------------------------------------------
async def run_grounding_eval(client, cases: list[GroundingCase]) -> EvalReport:
    """Score ``client`` (any ``HoloClient``) on ``cases``; return an EvalReport."""
    report = EvalReport()
    for case in cases:
        try:
            x, y = await client.localize(case.image_png, case.instruction)
            dist = math.hypot(x - case.expected[0], y - case.expected[1])
            report.results.append(
                CaseResult(
                    name=case.name,
                    instruction=case.instruction,
                    expected=case.expected,
                    predicted=(int(x), int(y)),
                    distance=dist,
                    tolerance_px=case.tolerance_px,
                    passed=dist <= case.tolerance_px,
                )
            )
        except Exception as exc:  # noqa: BLE001 — record, don't crash the whole eval
            report.results.append(
                CaseResult(
                    name=case.name,
                    instruction=case.instruction,
                    expected=case.expected,
                    predicted=(-1, -1),
                    distance=float("nan"),
                    tolerance_px=case.tolerance_px,
                    passed=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return report


# ---------------------------------------------------------------------------
# CLI — live / self-hosted gate
# ---------------------------------------------------------------------------
def _build_live_client():
    """Construct a real client from env, or return None if no endpoint is usable.

    ``GROUNDING_EVAL_BACKEND`` selects ``holo`` (hosted, needs ``HAI_API_KEY``) or
    ``selfhost`` (vLLM at ``HAI_BASE_URL``; key optional). Returns None when the
    selected backend has no credentials so the CLI can skip gracefully.
    """
    backend = os.getenv("GROUNDING_EVAL_BACKEND", "holo").strip().lower()
    base_url = os.getenv("HAI_BASE_URL", "https://api.hcompany.ai/v1/")
    model = os.getenv("HAI_MODEL", "holo3-1-35b-a3b")
    api_key = os.getenv("HAI_API_KEY", "")
    rpm = float(os.getenv("HAI_RPM", "10") or "10")

    if backend == "selfhost":
        from ghostpanel.engine.selfhost_client import (
            DEFAULT_SELFHOST_MODEL,
            SelfHostedHoloClient,
        )

        return SelfHostedHoloClient(
            api_key=api_key,
            base_url=base_url if "hcompany.ai" not in base_url else None,
            model=model if model != "holo3-1-35b-a3b" else DEFAULT_SELFHOST_MODEL,
            rpm=rpm if rpm > 100 else 1_000_000.0,
        )

    # hosted vendor
    if not api_key:
        return None
    from ghostpanel.engine.holo_client import LiveHoloClient

    return LiveHoloClient(api_key=api_key, base_url=base_url, model=model, rpm=rpm)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ghostpanel grounding eval gate")
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.5,
        help="fail (exit 1) if click accuracy is below this fraction (default 0.5)",
    )
    args = parser.parse_args(argv)

    client = _build_live_client()
    if client is None:
        print(
            "No inference credentials found (set HAI_API_KEY for the hosted "
            "backend, or GROUNDING_EVAL_BACKEND=selfhost + HAI_BASE_URL for a "
            "self-hosted vLLM endpoint). Skipping live eval.",
            file=sys.stderr,
        )
        return 0

    report = asyncio.run(run_grounding_eval(client, default_cases()))
    print(report.format())
    if report.accuracy < args.min_accuracy:
        print(
            f"\nGATE FAILED: accuracy {report.accuracy * 100:.1f}% "
            f"< required {args.min_accuracy * 100:.1f}%",
            file=sys.stderr,
        )
        return 1
    print(f"\nGATE PASSED: accuracy >= {args.min_accuracy * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
