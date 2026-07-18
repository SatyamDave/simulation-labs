"""Tests for cli/regression.py — compare() gate logic (Agent B).

RunReports are built by hand from the frozen contracts. regression.py is
implemented; the xfail(strict=False) guard is a safety net that flips to pass
if it were a stub.
"""

from __future__ import annotations

import pytest

from ghostpanel_contracts import PersonaOutcome, RunReport, SurvivalPoint


def _report(rows: list[tuple[str, bool]], *, heat=None) -> RunReport:
    """rows: list of (persona_id, completed). completion_rate derived over
    non-error personas (all here are success/stuck)."""
    survival = []
    for pid, completed in rows:
        survival.append(
            SurvivalPoint(
                persona_id=pid,
                persona_name=pid.title(),
                outcome=PersonaOutcome.SUCCESS if completed else PersonaOutcome.STUCK,
                steps_survived=10 if completed else 3,
                completed=completed,
            )
        )
    n = len(rows)
    completed_n = sum(1 for _, c in rows if c)
    heatmap_points = heat or []
    return RunReport(
        run_id="r",
        target_url="file:///x",
        task="t",
        survival=survival,
        heatmap_points=heatmap_points,
        completion_rate=(completed_n / n) if n else 0.0,
    )


def _is_stub() -> bool:
    from ghostpanel.cli.regression import compare

    try:
        compare(_report([("a", True)]), None, fail_under="last-passing")
        return False
    except NotImplementedError:
        return True
    except Exception:
        return False


pytestmark = pytest.mark.xfail(
    _is_stub(), reason="pending Agent B regression.py", strict=False
)


def test_absolute_threshold_pass():
    from ghostpanel.cli.regression import compare

    cur = _report([("a", True), ("b", True)])  # completion 1.0
    res = compare(cur, None, fail_under=0.8)
    assert res.passed is True
    assert res.threshold == 0.8


def test_absolute_threshold_fail():
    from ghostpanel.cli.regression import compare

    cur = _report([("a", True), ("b", False)])  # completion 0.5
    res = compare(cur, None, fail_under=0.8)
    assert res.passed is False


def test_last_passing_with_no_baseline_seeds_and_passes():
    from ghostpanel.cli.regression import compare

    cur = _report([("a", False), ("b", False)])  # even 0.0 completion
    res = compare(cur, None, fail_under="last-passing")
    assert res.passed is True
    assert res.completion_baseline is None


def test_last_passing_fails_when_completion_drops_and_flags_persona():
    from ghostpanel.cli.regression import compare

    baseline = _report([("a", True), ("b", True)])  # 1.0
    current = _report([("a", True), ("b", False)])  # 0.5, b regressed
    res = compare(current, baseline, fail_under="last-passing")
    assert res.passed is False
    regressed_ids = {d.persona_id for d in res.regressed_personas}
    assert regressed_ids == {"b"}
    (delta,) = res.regressed_personas
    assert delta.was is True and delta.now is False


def test_margin_tolerance_lets_small_drop_pass():
    from ghostpanel.cli.regression import compare

    baseline = _report([("a", True), ("b", True), ("c", True), ("d", True)])  # 1.0
    current = _report([("a", True), ("b", True), ("c", True), ("d", False)])  # 0.75
    # threshold = 1.0 - 0.3 = 0.7 <= 0.75 -> pass
    res = compare(current, baseline, fail_under="last-passing", margin=0.3)
    assert res.passed is True


# ---------------------------------------------------------------------------
# Functional verdict (E2E dimension): a broken flow fails even the first run.
# ---------------------------------------------------------------------------
def test_functional_fail_when_no_undegraded_probe_completes():
    from ghostpanel.cli.regression import compare, FUNCTIONAL_FAIL

    # fluent is the undegraded probe; nobody completes -> the flow is broken.
    cur = _report([("fluent", False), ("misclick-prone", False)])
    res = compare(cur, None, fail_under="last-passing",
                  functional_persona_ids={"fluent"})
    assert res.verdict == FUNCTIONAL_FAIL
    assert res.passed is False
    assert res.functional_ok is False
    assert "fluent" in res.reason


def test_functional_ok_but_behavioral_regression():
    from ghostpanel.cli.regression import compare, BEHAVIORAL_REGRESSION

    # Baseline: everyone finished. Now: fluent still finishes (flow works) but a
    # degraded segment regressed -> behavioral regression, not functional fail.
    base = _report([("fluent", True), ("misclick-prone", True)])
    cur = _report([("fluent", True), ("misclick-prone", False)])
    res = compare(cur, base, fail_under="last-passing",
                  functional_persona_ids={"fluent"})
    assert res.verdict == BEHAVIORAL_REGRESSION
    assert res.passed is False
    assert res.functional_ok is True


def test_functional_pass_seeds_baseline_when_probe_completes():
    from ghostpanel.cli.regression import compare, PASS

    cur = _report([("fluent", True), ("misclick-prone", False)])
    res = compare(cur, None, fail_under="last-passing",
                  functional_persona_ids={"fluent"})
    assert res.verdict == PASS
    assert res.passed is True
    assert res.functional_ok is True


def test_functional_dimension_absent_without_probe_ids():
    from ghostpanel.cli.regression import compare

    # No probe ids supplied -> functional dimension not assessed (back-compat).
    cur = _report([("fluent", False)])
    res = compare(cur, None, fail_under="last-passing")
    assert res.functional_ok is None
    assert res.passed is True  # first run seeds baseline


def test_errored_probe_is_not_functional_fail():
    """An infra ERROR on the only probe must NOT read as 'flow broken'."""
    from ghostpanel.cli.regression import compare
    from ghostpanel_contracts import PersonaOutcome, RunReport, SurvivalPoint

    cur = RunReport(
        run_id="r", target_url="x", task="t",
        survival=[
            SurvivalPoint(persona_id="fluent", persona_name="Fluent",
                          outcome=PersonaOutcome.ERROR, steps_survived=0, completed=False),
            SurvivalPoint(persona_id="misclick-prone", persona_name="Misclick-prone",
                          outcome=PersonaOutcome.STUCK, steps_survived=3, completed=False),
        ],
        completion_rate=0.0,
    )
    res = compare(cur, None, fail_under="last-passing",
                  functional_persona_ids={"fluent"})
    # fluent errored (infra), so functional dimension is unknown -> NOT functional_fail;
    # falls through to first-run seeding (pass).
    assert res.functional_ok is None
    assert res.verdict != "functional_fail"
    assert res.passed is True
