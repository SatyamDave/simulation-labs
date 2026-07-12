"""Run insights: composite score + accessibility-evidence mapping.

`build_insights` is the single seam between the report module (which computes
insights), the server (which writes them to `artifacts/<run_id>/insights.json`
after building the RunReport), and the frontend (which fetches that JSON and
renders the score panel + WCAG evidence table). The returned dict IS the wire
format — treat the top-level keys below as frozen:

{
  "ghostpanel_score": int,          # 0-100 composite survival score
  "agent_readiness": {              # derived from the "ai-agent" persona, or null
      "score": int,                 # 0-100
      "outcome": str,               # PersonaOutcome value
      "steps": int,
      "note": str,
  } | None,
  "wcag_findings": [                # one entry per evidenced failure
      {
        "persona_id": str,
        "persona_name": str,
        "criterion": str,           # e.g. "1.4.3"
        "name": str,                # e.g. "Contrast (Minimum)"
        "level": str,               # "A" | "AA" | "AAA"
        "standard_ref": str,        # EN 301 549 clause, e.g. "9.1.4.3"
        "evidence": str,            # grounded in the action trace / failure pixel
        "failure_step": int | None,
      }
  ],
  "summary": str,
  "meta": {                         # run identity, straight from RunReport
      "run_id": str, "target_url": str, "task": str,
      "generated_at": str, "personas": int,
  },
  "stats": {                        # defensible run/persona statistics
      "run": {
          "total_steps": int,
          "total_duration_s": float,          # sum of persona durations, 1 dp
          "avg_latency_ms": int,              # over steps with latency_ms>0
          "p95_latency_ms": int,              # same population (nearest-rank)
          "actions_by_type": {str: int},      # ActionType value -> count (nonzero only)
          "blocked_actions": int,             # steps with note == "policy_blocked"
          "personas_succeeded": int,
          "personas_abandoned": int,
          "personas_errored": int,
          "median_steps_to_abandon": int | None,
          "fastest_success_steps": int | None,
      },
      "personas": [                 # one per PersonaResult, in report order
          {
              "persona_id": str, "persona_name": str, "outcome": str,
              "steps": int, "steps_survived": int, "duration_s": float,
              "avg_latency_ms": int, "actions_by_type": {str: int},
              "blocked_actions": int,
              "max_repeated_action": int,     # longest run of identical captions
              "perturbations": [str],         # PerturbationKind values
          }
      ],
  },
  "survival_series": [              # stepped survival curve, non-error personas
      {"step": int, "alive": int}   # step = 0..max(steps_survived)
  ],
}
"""

from __future__ import annotations

import math
import statistics
from collections import Counter

from ghostpanel_contracts import (
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    PerturbationKind,
    RunReport,
    StepRecord,
)

from .builder import _steps_survived

# Note stamped on a StepRecord by the policy-enforcement layer when the action
# was blocked. Pinned string — the enforcement side writes exactly this.
POLICY_BLOCKED_NOTE = "policy_blocked"

# ---------------------------------------------------------------------------
# WCAG 2.2 success criteria evidenced by each degraded perception/actuation
# channel. EN 301 549 clause for web content = "9." + criterion number.
# A persona failing under a perturbation is *evidence of risk* against these
# criteria — never an automated conformance verdict.
# ---------------------------------------------------------------------------
_WCAG_BY_PERTURBATION: dict[PerturbationKind, list[tuple[str, str, str]]] = {
    PerturbationKind.BLUR: [
        ("1.4.3", "Contrast (Minimum)", "AA"),
        ("1.4.4", "Resize Text", "AA"),
    ],
    PerturbationKind.DOWNSCALE: [
        ("1.4.3", "Contrast (Minimum)", "AA"),
        ("1.4.4", "Resize Text", "AA"),
    ],
    PerturbationKind.CVD: [
        ("1.4.1", "Use of Color", "A"),
        ("1.4.3", "Contrast (Minimum)", "AA"),
    ],
    PerturbationKind.TREMOR: [
        ("2.5.8", "Target Size (Minimum)", "AA"),
        ("2.4.7", "Focus Visible", "AA"),
    ],
    PerturbationKind.SMALL_VIEWPORT: [
        ("1.4.10", "Reflow", "AA"),
    ],
    PerturbationKind.IMPATIENCE: [
        ("2.2.1", "Timing Adjustable", "A"),
        ("2.4.6", "Headings and Labels", "AA"),
    ],
    PerturbationKind.LOW_LITERACY: [
        ("3.1.5", "Reading Level", "AAA"),
        ("2.4.6", "Headings and Labels", "AA"),
    ],
}

# Extra channel keyed off PersonaConfig.language (no PerturbationKind for it).
_LANGUAGE_CRITERION = ("3.1.2", "Language of Parts", "AA")

# What each degraded channel models, for evidence prose.
_IMPAIRMENT_LABEL: dict[PerturbationKind, str] = {
    PerturbationKind.BLUR: "reduced visual acuity",
    PerturbationKind.DOWNSCALE: "reduced visual acuity",
    PerturbationKind.CVD: "impaired colour perception",
    PerturbationKind.TREMOR: "reduced motor precision",
    PerturbationKind.SMALL_VIEWPORT: "a small viewport",
    PerturbationKind.IMPATIENCE: "tight time and step budgets",
    PerturbationKind.LOW_LITERACY: "literal, low-inference reading",
}

_MAX_FINDINGS_PER_PERSONA = 2
_DEFAULT_MAX_STEPS = PersonaConfig(id="_", name="_").max_steps


def _credit(result: PersonaResult, persona: PersonaConfig | None) -> float:
    """Per-persona survival credit in [0, 1]. SUCCESS = 1.0; a non-success earns
    partial credit for distance travelled: 0.5 * (steps_survived / max_steps),
    capped at 0.5 — dying at step 2 drags the score down more than dying at 25."""
    if result.outcome == PersonaOutcome.SUCCESS:
        return 1.0
    max_steps = persona.max_steps if persona is not None else _DEFAULT_MAX_STEPS
    if max_steps <= 0:
        return 0.0
    return min(0.5, 0.5 * _steps_survived(result) / max_steps)


def _perturbation_desc(kind: PerturbationKind, persona: PersonaConfig) -> str:
    """Human tag for the mechanical degradation, e.g. 'blur σ=2.5'."""
    if kind == PerturbationKind.BLUR:
        return f"blur σ={persona.blur_sigma:g}"
    if kind == PerturbationKind.DOWNSCALE:
        return f"downscale ×{persona.downscale_factor:g}"
    if kind == PerturbationKind.CVD:
        cvd = persona.cvd_type.value if persona.cvd_type else "cvd"
        return f"{cvd} severity {persona.cvd_severity:g}"
    if kind == PerturbationKind.TREMOR:
        return f"tremor σ={persona.tremor_sigma_px:g}px"
    if kind == PerturbationKind.SMALL_VIEWPORT:
        return f"{persona.viewport.width}×{persona.viewport.height} viewport"
    if kind == PerturbationKind.IMPATIENCE:
        return f"max {persona.max_steps} steps / {persona.deadline_s:g}s"
    return "literal reading"  # LOW_LITERACY


def _last_caption(result: PersonaResult) -> str:
    if result.steps and result.steps[-1].action.caption:
        return result.steps[-1].action.caption
    return ""


def _evidence(
    result: PersonaResult,
    persona: PersonaConfig,
    channel_desc: str,
    impairment: str,
    criterion: str,
    criterion_name: str,
) -> str:
    """One grounded evidence sentence: trace facts first, risk framing last."""
    name = persona.name or persona.id
    step = result.failure_step if result.failure_step is not None else _steps_survived(result)
    text = f"{name} ({channel_desc}) abandoned at step {step}"
    if result.failure_coords is not None:
        x, y = result.failure_coords
        text += f" at ({x}, {y})"
    caption = _last_caption(result)
    if caption:
        text += f" — last action: {caption!r}"
    if result.failure_reason:
        text += f"; reason: {result.failure_reason}"
    text += (
        f". This trace is evidence that the flow is at risk under {impairment} "
        f"(maps to {criterion} {criterion_name}), not an automated conformance verdict."
    )
    return text


def _wcag_findings(
    result: PersonaResult, persona: PersonaConfig
) -> list[dict]:
    """Map the persona's ACTIVE perturbations (plus non-English language) to WCAG
    criteria; dedupe by criterion; keep the first `_MAX_FINDINGS_PER_PERSONA`."""
    # (criterion, name, level, channel_desc, impairment) in declared channel order
    applicable: list[tuple[str, str, str, str, str]] = []
    seen: set[str] = set()
    for kind in persona.active_perturbations:
        for criterion, crit_name, level in _WCAG_BY_PERTURBATION.get(kind, []):
            if criterion in seen:
                continue
            seen.add(criterion)
            applicable.append(
                (criterion, crit_name, level,
                 _perturbation_desc(kind, persona), _IMPAIRMENT_LABEL[kind])
            )
    if persona.language != "en":
        criterion, crit_name, level = _LANGUAGE_CRITERION
        if criterion not in seen:
            applicable.append(
                (criterion, crit_name, level,
                 f"language={persona.language}", "non-native language content")
            )

    findings: list[dict] = []
    for criterion, crit_name, level, channel_desc, impairment in applicable[
        :_MAX_FINDINGS_PER_PERSONA
    ]:
        findings.append(
            {
                "persona_id": persona.id,
                "persona_name": persona.name,
                "criterion": criterion,
                "name": crit_name,
                "level": level,
                "standard_ref": f"9.{criterion}",
                "evidence": _evidence(
                    result, persona, channel_desc, impairment, criterion, crit_name
                ),
                "failure_step": result.failure_step,
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Run / persona statistics (the "stats", "meta", "survival_series" keys)
# ---------------------------------------------------------------------------
def _latencies(steps: list[StepRecord]) -> list[int]:
    """Latency population: steps with a real (>0) Holo round-trip only."""
    return [s.latency_ms for s in steps if s.latency_ms > 0]


def _avg_ms(latencies: list[int]) -> int:
    return round(sum(latencies) / len(latencies)) if latencies else 0


def _p95_ms(latencies: list[int]) -> int:
    """Nearest-rank 95th percentile; 0 for an empty population."""
    if not latencies:
        return 0
    ordered = sorted(latencies)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _actions_by_type(steps: list[StepRecord]) -> dict[str, int]:
    """ActionType value -> count, nonzero types only (Counter omits zeros)."""
    return dict(Counter(s.action.type.value for s in steps))


def _blocked_actions(steps: list[StepRecord]) -> int:
    return sum(1 for s in steps if s.note == POLICY_BLOCKED_NOTE)


def _max_repeated_action(steps: list[StepRecord]) -> int:
    """Longest run of consecutive identical captions — the 'rage click' metric."""
    best = run = 0
    prev: str | None = None
    for step in steps:
        caption = step.action.caption
        run = run + 1 if caption == prev else 1
        prev = caption
        best = max(best, run)
    return best


def _persona_stats(result: PersonaResult, persona: PersonaConfig | None, name: str) -> dict:
    return {
        "persona_id": result.persona_id,
        "persona_name": name,
        "outcome": result.outcome.value,
        "steps": len(result.steps),
        "steps_survived": _steps_survived(result),
        "duration_s": round(result.duration_s, 1),
        "avg_latency_ms": _avg_ms(_latencies(result.steps)),
        "actions_by_type": _actions_by_type(result.steps),
        "blocked_actions": _blocked_actions(result.steps),
        "max_repeated_action": _max_repeated_action(result.steps),
        "perturbations": (
            [k.value for k in persona.active_perturbations] if persona else []
        ),
    }


def _run_stats(report: RunReport) -> dict:
    all_steps = [s for r in report.results for s in r.steps]
    latencies = _latencies(all_steps)
    successes = [r for r in report.results if r.outcome == PersonaOutcome.SUCCESS]
    errored = [r for r in report.results if r.outcome == PersonaOutcome.ERROR]
    abandoned = [
        r
        for r in report.results
        if r.outcome not in (PersonaOutcome.SUCCESS, PersonaOutcome.ERROR)
    ]
    return {
        "total_steps": len(all_steps),
        "total_duration_s": round(sum(r.duration_s for r in report.results), 1),
        "avg_latency_ms": _avg_ms(latencies),
        "p95_latency_ms": _p95_ms(latencies),
        "actions_by_type": _actions_by_type(all_steps),
        "blocked_actions": _blocked_actions(all_steps),
        "personas_succeeded": len(successes),
        "personas_abandoned": len(abandoned),
        "personas_errored": len(errored),
        "median_steps_to_abandon": (
            round(statistics.median(_steps_survived(r) for r in abandoned))
            if abandoned
            else None
        ),
        "fastest_success_steps": (
            min(_steps_survived(r) for r in successes) if successes else None
        ),
    }


def _survival_series(report: RunReport) -> list[dict]:
    """[{"step", "alive"}] for step = 0..max(steps_survived) over non-error
    personas. A persona is alive at step s if it succeeded or survived >= s."""
    entries = [
        (r.outcome == PersonaOutcome.SUCCESS, _steps_survived(r))
        for r in report.results
        if r.outcome != PersonaOutcome.ERROR
    ]
    if not entries:
        return []
    max_step = max(survived for _, survived in entries)
    return [
        {
            "step": step,
            "alive": sum(1 for ok, survived in entries if ok or survived >= step),
        }
        for step in range(max_step + 1)
    ]


def build_insights(report: RunReport, personas: list[PersonaConfig]) -> dict:
    """Compute the insights payload for a finished run. Pure; no I/O."""
    persona_by_id = {p.id: p for p in personas}

    def _name(pid: str) -> str:
        persona = persona_by_id.get(pid)
        return (persona.name if persona else "") or pid

    meta = {
        "run_id": report.run_id,
        "target_url": report.target_url,
        "task": report.task,
        "generated_at": report.generated_at,
        "personas": len(report.results),
    }
    stats = {
        "run": _run_stats(report),
        "personas": [
            _persona_stats(r, persona_by_id.get(r.persona_id), _name(r.persona_id))
            for r in report.results
        ],
    }
    survival_series = _survival_series(report)

    scored = [r for r in report.results if r.outcome != PersonaOutcome.ERROR]
    if not scored:
        return {
            "ghostpanel_score": 0,
            "agent_readiness": None,
            "wcag_findings": [],
            "summary": "No scoreable persona sessions (all errored).",
            "meta": meta,
            "stats": stats,
            "survival_series": survival_series,
        }

    # --- composite score: equal weight per non-error persona ---------------
    credits = {r.persona_id: _credit(r, persona_by_id.get(r.persona_id)) for r in scored}
    score = round(100 * sum(credits.values()) / len(scored))
    completed = sum(1 for r in scored if r.outcome == PersonaOutcome.SUCCESS)

    # --- agent readiness (the unimpaired "ai-agent" control) ---------------
    agent_readiness = None
    agent_result = next(
        (r for r in report.results if r.persona_id == "ai-agent"), None
    )
    if agent_result is not None:
        agent_steps = _steps_survived(agent_result)
        if agent_result.outcome == PersonaOutcome.SUCCESS:
            agent_score = 100
            note = "An unimpaired AI agent completed the task."
        elif agent_result.outcome == PersonaOutcome.ERROR:
            agent_score = 0
            note = (
                "The unimpaired AI agent session hit an infra error — "
                "agent-readiness could not be assessed."
            )
        else:
            agent_score = round(
                100 * _credit(agent_result, persona_by_id.get("ai-agent"))
            )
            note = (
                f"An unimpaired AI agent abandoned at step {agent_steps} — "
                "this site is not agent-ready."
            )
        agent_readiness = {
            "score": agent_score,
            "outcome": agent_result.outcome.value,
            "steps": agent_steps,
            "note": note,
        }

    # --- WCAG evidence-of-risk findings ------------------------------------
    findings: list[dict] = []
    for result in scored:
        if result.outcome == PersonaOutcome.SUCCESS:
            continue
        persona = persona_by_id.get(result.persona_id)
        if persona is None:
            continue  # no config -> no perturbation channels to map
        findings.extend(_wcag_findings(result, persona))

    # --- summary ------------------------------------------------------------
    summary = f"{completed}/{len(scored)} personas completed the task"
    failures = [r for r in scored if r.outcome != PersonaOutcome.SUCCESS]
    if failures:
        worst = min(
            failures, key=lambda r: (credits[r.persona_id], _steps_survived(r))
        )
        summary += (
            f"; worst performer was {_name(worst.persona_id)} "
            f"({worst.outcome.value} at step {_steps_survived(worst)})"
        )
    summary += "."
    if agent_readiness is not None:
        summary += f" {agent_readiness['note']}"

    return {
        "ghostpanel_score": score,
        "agent_readiness": agent_readiness,
        "wcag_findings": findings,
        "summary": summary,
        "meta": meta,
        "stats": stats,
        "survival_series": survival_series,
    }
