"""Tests for build_insights: score arithmetic, agent readiness, WCAG mapping."""

from __future__ import annotations

from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    PerturbationKind,
    StepRecord,
    Viewport,
)

from ghostpanel.report.builder import SurvivalReportBuilder
from ghostpanel.report.insights import build_insights


def _persona(pid: str, **overrides) -> PersonaConfig:
    return PersonaConfig(id=pid, name=overrides.pop("name", pid.title()), **overrides)


def _result(pid: str, outcome: PersonaOutcome, **overrides) -> PersonaResult:
    return PersonaResult(persona_id=pid, outcome=outcome, **overrides)


def _step(
    pid: str,
    i: int,
    action_type: ActionType = ActionType.CLICK,
    caption: str = "",
    latency: int = 0,
    note: str = "",
) -> StepRecord:
    return StepRecord(
        persona_id=pid,
        step=i,
        action=Action(type=action_type, caption=caption),
        latency_ms=latency,
        note=note,
    )


def _insights(results: list[PersonaResult], personas: list[PersonaConfig]) -> dict:
    report = SurvivalReportBuilder().build(
        "run-x", "http://example.test", "Sign up", results, personas
    )
    return build_insights(report, personas)


# ---------------------------------------------------------------------------
# ghostpanel_score
# ---------------------------------------------------------------------------
def test_all_success_scores_100():
    personas = [_persona("a"), _persona("b")]
    results = [
        _result("a", PersonaOutcome.SUCCESS),
        _result("b", PersonaOutcome.SUCCESS),
    ]
    assert _insights(results, personas)["ghostpanel_score"] == 100


def test_partial_credit_scales_with_steps_survived():
    # non-success credit = 0.5 * steps/max_steps -> failing later scores higher
    personas = [_persona("early", max_steps=30), _persona("late", max_steps=30)]
    early = _insights(
        [_result("early", PersonaOutcome.STUCK, failure_step=2)], [personas[0]]
    )
    late = _insights(
        [_result("late", PersonaOutcome.STUCK, failure_step=25)], [personas[1]]
    )
    # 0.5 * 2/30 = 0.033 -> 3 ; 0.5 * 25/30 = 0.4166 -> 42
    assert early["ghostpanel_score"] == 3
    assert late["ghostpanel_score"] == 42
    assert late["ghostpanel_score"] > early["ghostpanel_score"]


def test_partial_credit_capped_at_half():
    # steps beyond max_steps never earn more than 0.5 credit -> 50
    personas = [_persona("p", max_steps=10)]
    results = [_result("p", PersonaOutcome.STEP_BUDGET, failure_step=99)]
    assert _insights(results, personas)["ghostpanel_score"] == 50


def test_mixed_success_and_failure_average():
    # success (1.0) + failure at 15/30 (0.25) -> mean 0.625 -> 62
    personas = [_persona("winner"), _persona("loser", max_steps=30)]
    results = [
        _result("winner", PersonaOutcome.SUCCESS),
        _result("loser", PersonaOutcome.STUCK, failure_step=15),
    ]
    assert _insights(results, personas)["ghostpanel_score"] == 62


def test_error_outcomes_excluded_from_score():
    personas = [_persona("a"), _persona("crashy")]
    results = [_result("a", PersonaOutcome.SUCCESS)]
    baseline = _insights(results, personas)["ghostpanel_score"]
    with_error = _insights(
        results + [_result("crashy", PersonaOutcome.ERROR)], personas
    )["ghostpanel_score"]
    assert baseline == with_error == 100


def test_all_errored_returns_zero_and_no_findings():
    personas = [_persona("crashy")]
    payload = _insights([_result("crashy", PersonaOutcome.ERROR)], personas)
    assert payload["ghostpanel_score"] == 0
    assert payload["agent_readiness"] is None
    assert payload["wcag_findings"] == []


# ---------------------------------------------------------------------------
# agent_readiness
# ---------------------------------------------------------------------------
def test_agent_readiness_success():
    personas = [_persona("ai-agent", name="Agent (headless AI)", max_steps=40)]
    payload = _insights([_result("ai-agent", PersonaOutcome.SUCCESS)], personas)
    ar = payload["agent_readiness"]
    assert ar["score"] == 100
    assert ar["outcome"] == "success"
    assert "completed the task" in ar["note"]


def test_agent_readiness_failure_partial_credit_and_note():
    personas = [_persona("ai-agent", max_steps=40)]
    payload = _insights(
        [_result("ai-agent", PersonaOutcome.STUCK, failure_step=8)], personas
    )
    ar = payload["agent_readiness"]
    # 100 * 0.5 * 8/40 = 10
    assert ar["score"] == 10
    assert ar["outcome"] == "stuck"
    assert ar["steps"] == 8
    assert "abandoned at step 8" in ar["note"]
    assert "not agent-ready" in ar["note"]
    assert ar["note"] in payload["summary"]


def test_agent_readiness_absent_without_ai_agent():
    personas = [_persona("grandma-72")]
    payload = _insights([_result("grandma-72", PersonaOutcome.STUCK)], personas)
    assert payload["agent_readiness"] is None


# ---------------------------------------------------------------------------
# wcag_findings
# ---------------------------------------------------------------------------
def _findings_for(persona: PersonaConfig, result: PersonaResult) -> list[dict]:
    return _insights([result], [persona])["wcag_findings"]


def test_wcag_mapping_per_perturbation():
    cases = [
        ([PerturbationKind.BLUR], {"blur_sigma": 2.5}, ["1.4.3", "1.4.4"]),
        ([PerturbationKind.DOWNSCALE], {"downscale_factor": 0.4}, ["1.4.3", "1.4.4"]),
        ([PerturbationKind.CVD], {"cvd_type": "deutan", "cvd_severity": 0.9},
         ["1.4.1", "1.4.3"]),
        ([PerturbationKind.TREMOR], {"tremor_sigma_px": 14.0}, ["2.5.8", "2.4.7"]),
        ([PerturbationKind.SMALL_VIEWPORT],
         {"viewport": Viewport(width=390, height=844)}, ["1.4.10"]),
        ([PerturbationKind.IMPATIENCE], {"max_steps": 8}, ["2.2.1", "2.4.6"]),
        ([PerturbationKind.LOW_LITERACY], {}, ["3.1.5", "2.4.6"]),
    ]
    for kinds, fields, expected in cases:
        persona = _persona("p", active_perturbations=kinds, **fields)
        findings = _findings_for(
            persona, _result("p", PersonaOutcome.STUCK, failure_step=3)
        )
        assert [f["criterion"] for f in findings] == expected, kinds
        for f in findings:
            assert f["standard_ref"] == f"9.{f['criterion']}"
            assert f["level"] in {"A", "AA", "AAA"}
            assert f["persona_id"] == "p"


def test_non_english_language_maps_language_of_parts():
    persona = _persona("luca", language="it")
    findings = _findings_for(
        persona, _result("luca", PersonaOutcome.TIME_BUDGET, failure_step=5)
    )
    assert [f["criterion"] for f in findings] == ["3.1.2"]
    assert findings[0]["name"] == "Language of Parts"
    assert findings[0]["standard_ref"] == "9.3.1.2"


def test_findings_capped_at_two_and_deduped():
    # cvd -> 1.4.1, 1.4.3 ; blur would re-add 1.4.3 (dedupe) then 1.4.4 (over cap)
    persona = _persona(
        "p",
        active_perturbations=[PerturbationKind.CVD, PerturbationKind.BLUR],
        cvd_type="deutan",
        cvd_severity=0.9,
        blur_sigma=2.0,
    )
    findings = _findings_for(persona, _result("p", PersonaOutcome.STUCK, failure_step=4))
    assert [f["criterion"] for f in findings] == ["1.4.1", "1.4.3"]


def test_success_and_error_personas_produce_no_findings():
    personas = [
        _persona("ok", active_perturbations=[PerturbationKind.BLUR], blur_sigma=2.0),
        _persona("boom", active_perturbations=[PerturbationKind.TREMOR],
                 tremor_sigma_px=9.0),
    ]
    results = [
        _result("ok", PersonaOutcome.SUCCESS),
        _result("boom", PersonaOutcome.ERROR, failure_step=1),
    ]
    assert _insights(results, personas)["wcag_findings"] == []


def test_evidence_is_grounded_in_the_trace():
    persona = _persona(
        "grandma-72",
        name="Margaret, 72",
        active_perturbations=[PerturbationKind.BLUR],
        blur_sigma=2.5,
        max_steps=12,
    )
    step = StepRecord(
        persona_id="grandma-72",
        step=6,
        action=Action(type=ActionType.CLICK, x=431, y=502,
                      caption="Click 'Explore plans' again"),
    )
    result = _result(
        "grandma-72",
        PersonaOutcome.STUCK,
        steps=[step],
        failure_step=7,
        failure_coords=(431, 502),
        failure_reason="repeated action: Click 'Explore plans' again",
    )
    findings = _findings_for(persona, result)
    assert findings, "expected at least one finding"
    evidence = findings[0]["evidence"]
    assert "step 7" in evidence                       # failure_step
    assert "(431, 502)" in evidence                   # failure_coords
    assert "Explore plans" in evidence                # last action caption
    assert "repeated action" in evidence              # failure_reason
    assert "Margaret, 72" in evidence
    assert "σ=2.5" in evidence                        # active perturbation strength
    assert "not an automated conformance verdict" in evidence
    assert findings[0]["failure_step"] == 7


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------
def test_meta_passthrough_from_run_report():
    personas = [_persona("a"), _persona("b")]
    results = [
        _result("a", PersonaOutcome.SUCCESS),
        _result("b", PersonaOutcome.ERROR),
    ]
    report = SurvivalReportBuilder().build(
        "run-42", "http://target.test", "Cancel plan", results, personas
    )
    meta = build_insights(report, personas)["meta"]
    assert meta == {
        "run_id": "run-42",
        "target_url": "http://target.test",
        "task": "Cancel plan",
        "generated_at": report.generated_at,
        "personas": 2,
    }


# ---------------------------------------------------------------------------
# stats — latency
# ---------------------------------------------------------------------------
def test_avg_latency_excludes_zero_latency_steps():
    personas = [_persona("p")]
    steps = [
        _step("p", 0, latency=100),
        _step("p", 1, latency=0),      # excluded from the population
        _step("p", 2, latency=200),
        _step("p", 3, latency=300),
        _step("p", 4, latency=0),      # excluded
    ]
    payload = _insights([_result("p", PersonaOutcome.SUCCESS, steps=steps)], personas)
    assert payload["stats"]["run"]["avg_latency_ms"] == 200  # mean(100,200,300)
    assert payload["stats"]["personas"][0]["avg_latency_ms"] == 200
    assert payload["stats"]["run"]["total_steps"] == 5       # zero-latency still counted


def test_avg_latency_zero_when_no_positive_latencies():
    personas = [_persona("p")]
    steps = [_step("p", 0), _step("p", 1)]
    payload = _insights([_result("p", PersonaOutcome.SUCCESS, steps=steps)], personas)
    assert payload["stats"]["run"]["avg_latency_ms"] == 0
    assert payload["stats"]["run"]["p95_latency_ms"] == 0
    assert payload["stats"]["personas"][0]["avg_latency_ms"] == 0


def test_p95_latency_nearest_rank():
    personas = [_persona("p")]
    # latencies 10, 20, ..., 200 -> nearest-rank p95 of 20 values = 19th = 190
    steps = [_step("p", i, latency=(i + 1) * 10) for i in range(20)]
    payload = _insights([_result("p", PersonaOutcome.SUCCESS, steps=steps)], personas)
    assert payload["stats"]["run"]["p95_latency_ms"] == 190


# ---------------------------------------------------------------------------
# stats — action mix / blocked / rage-repeat
# ---------------------------------------------------------------------------
def test_actions_by_type_counts_only_nonzero():
    personas = [_persona("p")]
    steps = [
        _step("p", 0, ActionType.CLICK),
        _step("p", 1, ActionType.CLICK),
        _step("p", 2, ActionType.WRITE),
        _step("p", 3, ActionType.SCROLL),
        _step("p", 4, ActionType.CLICK),
    ]
    payload = _insights([_result("p", PersonaOutcome.SUCCESS, steps=steps)], personas)
    expected = {"click": 3, "write": 1, "scroll": 1}
    assert payload["stats"]["run"]["actions_by_type"] == expected
    assert payload["stats"]["personas"][0]["actions_by_type"] == expected


def test_blocked_actions_counted_via_policy_blocked_note():
    personas = [_persona("p"), _persona("q")]
    results = [
        _result(
            "p",
            PersonaOutcome.STUCK,
            steps=[
                _step("p", 0, note="policy_blocked"),
                _step("p", 1, note="just a note"),     # not blocked
                _step("p", 2, note="policy_blocked"),
            ],
        ),
        _result("q", PersonaOutcome.SUCCESS, steps=[_step("q", 0)]),
    ]
    payload = _insights(results, personas)
    assert payload["stats"]["run"]["blocked_actions"] == 2
    assert payload["stats"]["personas"][0]["blocked_actions"] == 2
    assert payload["stats"]["personas"][1]["blocked_actions"] == 0


def test_max_repeated_action_longest_caption_run():
    personas = [_persona("p"), _persona("empty")]
    steps = [
        _step("p", 0, caption="Click 'Buy'"),
        _step("p", 1, caption="Click 'Buy'"),
        _step("p", 2, caption="Click 'Buy'"),
        _step("p", 3, caption="Scroll down"),
        _step("p", 4, caption="Click 'Buy'"),   # non-consecutive: new run of 1
        _step("p", 5, caption="Click 'Buy'"),
    ]
    payload = _insights(
        [
            _result("p", PersonaOutcome.STUCK, steps=steps, failure_step=6),
            _result("empty", PersonaOutcome.ERROR),
        ],
        personas,
    )
    assert payload["stats"]["personas"][0]["max_repeated_action"] == 3
    assert payload["stats"]["personas"][1]["max_repeated_action"] == 0


# ---------------------------------------------------------------------------
# stats — run-level roster counters
# ---------------------------------------------------------------------------
def test_run_counters_median_and_fastest_success():
    personas = [
        _persona("fast"),
        _persona("slow"),
        _persona("quit-early"),
        _persona("quit-late"),
        _persona("crashy"),
    ]
    results = [
        _result(
            "fast",
            PersonaOutcome.SUCCESS,
            steps=[_step("fast", i) for i in range(4)],
            duration_s=10.04,
        ),
        _result(
            "slow",
            PersonaOutcome.SUCCESS,
            steps=[_step("slow", i) for i in range(9)],
            duration_s=20.0,
        ),
        _result("quit-early", PersonaOutcome.STUCK, failure_step=3, duration_s=5.0),
        _result("quit-late", PersonaOutcome.TIME_BUDGET, failure_step=5, duration_s=30.0),
        _result("crashy", PersonaOutcome.ERROR, failure_step=1, duration_s=1.0),
    ]
    run = _insights(results, personas)["stats"]["run"]
    assert run["personas_succeeded"] == 2
    assert run["personas_abandoned"] == 2
    assert run["personas_errored"] == 1
    assert run["median_steps_to_abandon"] == 4       # median(3, 5)
    assert run["fastest_success_steps"] == 4
    assert run["total_steps"] == 13
    assert run["total_duration_s"] == 66.0           # 10.04+20+5+30+1 -> 1 dp


def test_median_steps_to_abandon_null_without_abandons():
    personas = [_persona("a")]
    run = _insights([_result("a", PersonaOutcome.SUCCESS)], personas)["stats"]["run"]
    assert run["median_steps_to_abandon"] is None
    assert run["fastest_success_steps"] == 0         # success with no recorded steps


def test_persona_stats_perturbations_and_order():
    personas = [
        _persona("baseline"),
        _persona(
            "shaky",
            active_perturbations=[PerturbationKind.TREMOR, PerturbationKind.BLUR],
            tremor_sigma_px=9.0,
            blur_sigma=2.0,
        ),
    ]
    results = [
        _result("shaky", PersonaOutcome.STUCK, failure_step=2, duration_s=3.14),
        _result("baseline", PersonaOutcome.SUCCESS),
    ]
    rows = _insights(results, personas)["stats"]["personas"]
    # report order == results order, not personas order
    assert [r["persona_id"] for r in rows] == ["shaky", "baseline"]
    assert rows[0]["perturbations"] == ["tremor", "blur"]
    assert rows[0]["outcome"] == "stuck"
    assert rows[0]["steps_survived"] == 2
    assert rows[0]["duration_s"] == 3.1
    assert rows[1]["perturbations"] == []
    assert rows[1]["persona_name"] == "Baseline"


# ---------------------------------------------------------------------------
# survival_series
# ---------------------------------------------------------------------------
def test_survival_series_mixed_roster_exact():
    personas = [_persona("win"), _persona("q2"), _persona("q4"), _persona("boom")]
    results = [
        _result(
            "win",
            PersonaOutcome.SUCCESS,
            steps=[_step("win", i) for i in range(5)],   # steps_survived = 5
        ),
        _result("q2", PersonaOutcome.STUCK, failure_step=2),
        _result("q4", PersonaOutcome.STEP_BUDGET, failure_step=4),
        _result("boom", PersonaOutcome.ERROR, failure_step=1),  # excluded
    ]
    series = _insights(results, personas)["survival_series"]
    assert series == [
        {"step": 0, "alive": 3},
        {"step": 1, "alive": 3},
        {"step": 2, "alive": 3},
        {"step": 3, "alive": 2},
        {"step": 4, "alive": 2},
        {"step": 5, "alive": 1},
    ]


def test_survival_series_empty_when_all_error():
    personas = [_persona("boom")]
    payload = _insights([_result("boom", PersonaOutcome.ERROR)], personas)
    assert payload["survival_series"] == []
    # the all-error early return still ships the additive keys
    assert payload["meta"]["personas"] == 1
    assert payload["stats"]["run"]["personas_errored"] == 1


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
def test_summary_names_completions_and_worst_performer():
    personas = [
        _persona("winner"),
        _persona("bad", name="Bad Bot", max_steps=30),
        _persona("worse", name="Worse Bot", max_steps=30),
    ]
    results = [
        _result("winner", PersonaOutcome.SUCCESS),
        _result("bad", PersonaOutcome.STUCK, failure_step=10),
        _result("worse", PersonaOutcome.STUCK, failure_step=2),
    ]
    summary = _insights(results, personas)["summary"]
    assert "1/3" in summary
    assert "Worse Bot" in summary
    assert "step 2" in summary
