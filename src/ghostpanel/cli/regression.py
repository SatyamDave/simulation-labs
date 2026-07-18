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


# Gate verdicts. FUNCTIONAL_FAIL and BEHAVIORAL_REGRESSION both fail the merge but
# mean different things: FUNCTIONAL_FAIL = the flow is broken (even an undegraded
# agent can't finish it — like a red E2E test); BEHAVIORAL_REGRESSION = the flow
# works, but fewer degraded human segments can complete it than the last passing run.
PASS = "pass"
FUNCTIONAL_FAIL = "functional_fail"
BEHAVIORAL_REGRESSION = "behavioral_regression"


@dataclass
class RegressionResult:
    passed: bool
    reason: str                                   # human one-liner
    completion_now: float
    completion_baseline: float | None
    threshold: float                              # effective numeric bar used
    fail_under: str                               # "last-passing" or the float as text
    # verdict distinguishes the two failure modes (see the constants above).
    verdict: str = PASS
    # None => no functional probe was supplied (functional dimension not assessed).
    functional_ok: bool | None = None
    functional_probe_ids: list[str] = field(default_factory=list)
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


def _functional_ok(current: RunReport, probe_ids: list[str]) -> bool:
    """Did the flow work at all? True if ANY undegraded probe persona completed.

    The probes are the swarm's baseline (no perturbations) agents — the closest
    thing to a conventional E2E test. If not one of them can finish, the flow is
    broken, not merely hard for impaired users.
    """
    rows = _completed_by_persona(current)
    return any(
        (rows[pid].completed if pid in rows else False) for pid in probe_ids
    )


def compare(
    current: RunReport,
    baseline: RunReport | None,
    *,
    fail_under: float | str,
    margin: float = 0.0,
    functional_persona_ids: set[str] | list[str] | None = None,
) -> RegressionResult:
    """Decide whether `current` passes the gate.

    - fail_under is a float (0..1 absolute completion bar) OR "last-passing"
      (bar = baseline.completion_rate; `margin` is the tolerated drop).
    - No baseline + "last-passing" => pass (first run seeds the baseline).
    - ``functional_persona_ids`` are the undegraded probe personas (no
      perturbations, e.g. ``fluent``). If supplied and NONE of them completed,
      the verdict is FUNCTIONAL_FAIL — the flow is broken — and the run fails
      regardless of the behavioral bar or whether a baseline exists (a red E2E
      test blocks the merge on its own). If omitted, the functional dimension is
      simply not assessed (verdict is PASS/BEHAVIORAL_REGRESSION as before).
    - Populate regressed_personas (succeeded before, fail now) and new_dead_zones
      (heat clusters present now but not in the baseline) for the CI output.
    """
    completion_now = _completion(current)
    completion_baseline = _completion(baseline) if baseline is not None else None

    # --- functional gate (E2E): does the flow work at all? Checked FIRST so a
    #     broken flow fails even on the first, baseline-seeding run. ---
    probe_ids = sorted(set(functional_persona_ids)) if functional_persona_ids else []
    functional_ok: bool | None = _functional_ok(current, probe_ids) if probe_ids else None

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

    # --- functional gate first: a broken flow (no undegraded probe finished)
    #     fails the merge on its own, baseline or not. ---
    fail_under_str = LAST_PASSING if isinstance(fail_under, str) else f"{float(fail_under):g}"
    if functional_ok is False:
        probes = ", ".join(probe_ids)
        return RegressionResult(
            passed=False,
            reason=(
                f"functional failure — the flow is broken: the undegraded baseline "
                f"agent{'s' if len(probe_ids) != 1 else ''} ({probes}) could not "
                f"complete it"
            ),
            completion_now=completion_now,
            completion_baseline=completion_baseline,
            threshold=0.0,
            fail_under=fail_under_str,
            verdict=FUNCTIONAL_FAIL,
            functional_ok=False,
            functional_probe_ids=probe_ids,
            regressed_personas=regressed,
            new_dead_zones=new_dead_zones,
        )

    # --- behavioral verdict ---
    is_last_passing = isinstance(fail_under, str)
    if is_last_passing:
        if str(fail_under) != LAST_PASSING:
            raise ValueError(
                f"fail_under must be a float or {LAST_PASSING!r}, got {fail_under!r}"
            )
        if baseline is None:
            return RegressionResult(
                passed=True,
                reason="first run — seeding baseline",
                completion_now=completion_now,
                completion_baseline=None,
                threshold=0.0,
                fail_under=LAST_PASSING,
                verdict=PASS,
                functional_ok=functional_ok,
                functional_probe_ids=probe_ids,
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
        verdict=PASS if passed else BEHAVIORAL_REGRESSION,
        functional_ok=functional_ok,
        functional_probe_ids=probe_ids,
        regressed_personas=regressed,
        new_dead_zones=new_dead_zones,
    )
