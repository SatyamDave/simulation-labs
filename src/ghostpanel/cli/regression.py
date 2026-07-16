"""Regression engine — Agent B owns this file.

STUB: implement per PHASE1_SPEC.md. Signatures below are FROZEN (main.py and
ci_output.py import them). This is the core "behavioral test": diff the current
RunReport against a stored baseline and decide pass/fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ghostpanel_contracts import PersonaOutcome, RunReport

LAST_PASSING = "last-passing"
# Grid size (px) used to cluster heatmap points into dead zones.
_DEAD_ZONE_GRID = 40


@dataclass
class PersonaDelta:
    persona_id: str
    persona_name: str
    was: bool          # completed in the baseline
    now: bool          # completed in the current run
    steps_was: int
    steps_now: int


@dataclass
class RegressionResult:
    passed: bool
    reason: str                                   # human one-liner
    completion_now: float
    completion_baseline: float | None
    threshold: float                              # effective numeric bar used
    fail_under: str                               # "last-passing" or the float as text
    regressed_personas: list[PersonaDelta] = field(default_factory=list)
    new_dead_zones: list[tuple[int, int]] = field(default_factory=list)


def _completion_from_survival(report: RunReport) -> float:
    """Recompute completion from the survival curve.

    Denominator excludes ERROR (infra failure, not a real abandon). Numerator
    counts SUCCESS. Guards divide-by-zero (returns 0.0 when no non-error personas).
    """
    considered = [p for p in report.survival if p.outcome != PersonaOutcome.ERROR]
    if not considered:
        return 0.0
    succeeded = sum(1 for p in considered if p.outcome == PersonaOutcome.SUCCESS)
    return succeeded / len(considered)


def _completion(report: RunReport) -> float:
    """Prefer the report's own completion_rate; fall back to a recomputed value
    when the field is 0/absent (robust to reports that didn't stamp it)."""
    reported = getattr(report, "completion_rate", 0.0) or 0.0
    if reported > 0.0:
        return float(reported)
    return _completion_from_survival(report)


def _completed_by_persona(report: RunReport) -> dict[str, "SurvivalRow"]:
    """Map persona_id -> (completed, steps_survived, name) from the survival curve."""
    out: dict[str, SurvivalRow] = {}
    for p in report.survival:
        out[p.persona_id] = SurvivalRow(
            name=p.persona_name or p.persona_id,
            completed=bool(p.completed),
            steps=int(p.steps_survived),
        )
    return out


@dataclass
class SurvivalRow:
    name: str
    completed: bool
    steps: int


def _clustered_zones(report: RunReport, grid: int = _DEAD_ZONE_GRID) -> list[tuple[int, int]]:
    """Cluster heatmap points onto a `grid`-px lattice, deduped and sorted.

    Each point is snapped to the nearest grid cell centre; identical cells
    collapse to one representative (x, y). Deterministic ordering."""
    seen: set[tuple[int, int]] = set()
    for hp in report.heatmap_points:
        cx = int(round(hp.x / grid)) * grid
        cy = int(round(hp.y / grid)) * grid
        seen.add((cx, cy))
    return sorted(seen)


def compare(
    current: RunReport,
    baseline: RunReport | None,
    *,
    fail_under: float | str,
    margin: float = 0.0,
) -> RegressionResult:
    """Decide whether `current` passes the gate.

    - fail_under is a float (0..1 absolute completion bar) OR "last-passing"
      (bar = baseline.completion_rate; `margin` is the tolerated drop).
    - No baseline + "last-passing" => pass (first run seeds the baseline).
    - Populate regressed_personas (succeeded before, fail now) and new_dead_zones
      (heat clusters present now but not in the baseline) for the CI output.
    """
    completion_now = _completion(current)
    completion_baseline = _completion(baseline) if baseline is not None else None

    # --- regressed personas: completed in baseline, not in current ---
    regressed: list[PersonaDelta] = []
    if baseline is not None:
        base_rows = _completed_by_persona(baseline)
        cur_rows = _completed_by_persona(current)
        for pid, brow in base_rows.items():
            crow = cur_rows.get(pid)
            now_completed = bool(crow.completed) if crow is not None else False
            if brow.completed and not now_completed:
                regressed.append(
                    PersonaDelta(
                        persona_id=pid,
                        persona_name=(crow.name if crow is not None else brow.name),
                        was=True,
                        now=now_completed,
                        steps_was=brow.steps,
                        steps_now=(crow.steps if crow is not None else 0),
                    )
                )
        regressed.sort(key=lambda d: d.persona_id)

    # --- new dead zones: clustered heat cells present now but not in baseline ---
    new_dead_zones: list[tuple[int, int]] = []
    if baseline is not None:
        base_zones = set(_clustered_zones(baseline))
        new_dead_zones = [z for z in _clustered_zones(current) if z not in base_zones]

    # --- verdict ---
    is_last_passing = isinstance(fail_under, str)
    if is_last_passing:
        if str(fail_under) != LAST_PASSING:
            raise ValueError(
                f"fail_under must be a float or {LAST_PASSING!r}, got {fail_under!r}"
            )
        fail_under_str = LAST_PASSING
        if baseline is None:
            return RegressionResult(
                passed=True,
                reason="first run — seeding baseline",
                completion_now=completion_now,
                completion_baseline=None,
                threshold=0.0,
                fail_under=LAST_PASSING,
                regressed_personas=[],
                new_dead_zones=[],
            )
        threshold = float(completion_baseline or 0.0) - float(margin)
        passed = completion_now >= threshold
        rel = "≥" if passed else "<"
        reason = (
            f"completion {completion_now:.2f} {rel} last-passing bar {threshold:.2f}"
        )
        if not passed and regressed:
            n = len(regressed)
            reason += f" ({n} persona{'s' if n != 1 else ''} regressed)"
    else:
        threshold = float(fail_under)
        fail_under_str = f"{threshold:g}"
        passed = completion_now >= threshold
        rel = "≥" if passed else "<"
        reason = f"completion {completion_now:.2f} {rel} {threshold:.2f}"

    return RegressionResult(
        passed=passed,
        reason=reason,
        completion_now=completion_now,
        completion_baseline=completion_baseline,
        threshold=threshold,
        fail_under=fail_under_str,
        regressed_personas=regressed,
        new_dead_zones=new_dead_zones,
    )
