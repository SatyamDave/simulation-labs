"""Tests for cli/ci_output.py — CI-native formatters (Agent C).

ci_output.py is a stub at time of writing, so calls are wrapped with an
xfail(strict=False) guard that flips to pass once Agent C lands. RunReport /
RegressionResult are built by hand from the frozen contracts.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from ghostpanel_contracts import PersonaOutcome, RunReport, SurvivalPoint

from ghostpanel.cli.regression import RegressionResult


def _report() -> RunReport:
    return RunReport(
        run_id="run-123",
        target_url="file:///x",
        task="Sign up",
        survival=[
            SurvivalPoint(
                persona_id="power-user",
                persona_name="Alex",
                outcome=PersonaOutcome.SUCCESS,
                steps_survived=8,
                completed=True,
            ),
            SurvivalPoint(
                persona_id="grandma-72",
                persona_name="Margaret",
                outcome=PersonaOutcome.STUCK,
                steps_survived=4,
                completed=False,
            ),
        ],
        completion_rate=0.5,
    )


def _reg(passed: bool) -> RegressionResult:
    return RegressionResult(
        passed=passed,
        reason="completion 0.50 < bar 1.00" if not passed else "completion 1.00 ≥ bar 0.80",
        completion_now=0.5 if not passed else 1.0,
        completion_baseline=1.0,
        threshold=1.0 if not passed else 0.8,
        fail_under="last-passing",
    )


def _is_stub() -> bool:
    from ghostpanel.cli import ci_output

    try:
        ci_output.junit_xml(_report(), _reg(True))
        return False
    except NotImplementedError:
        return True
    except Exception:
        return False


pytestmark = pytest.mark.xfail(
    _is_stub(), reason="pending Agent C ci_output.py", strict=False
)


def test_junit_xml_parses_and_marks_failures():
    from ghostpanel.cli.ci_output import junit_xml

    xml = junit_xml(_report(), _reg(False))
    root = ET.fromstring(xml)  # parses as valid XML
    cases = list(root.iter("testcase"))
    assert len(cases) == 2  # one per persona

    def _ident(c) -> str:
        return (c.get("name") or "") + " " + (c.get("classname") or "")

    def _failed(c) -> bool:
        return c.find("failure") is not None or c.find("error") is not None

    # exactly the one non-completing persona is marked failed
    failed_cases = [c for c in cases if _failed(c)]
    assert len(failed_cases) == 1
    # the failing testcase references the stuck persona (by name or id);
    # the successful persona's testcase is not marked failed.
    (failed,) = failed_cases
    assert "Margaret" in _ident(failed) or "grandma-72" in _ident(failed)
    passed_cases = [c for c in cases if not _failed(c)]
    (passed,) = passed_cases
    assert "Alex" in _ident(passed) or "power-user" in _ident(passed)


def test_pr_comment_has_marker_and_verdict_word():
    from ghostpanel.cli.ci_output import pr_comment_md

    md_fail = pr_comment_md(_report(), _reg(False))
    assert "<!-- simulationlabs-gate -->" in md_fail
    assert "FAIL" in md_fail.upper()

    md_pass = pr_comment_md(_report(), _reg(True))
    assert "<!-- simulationlabs-gate -->" in md_pass
    assert "PASS" in md_pass.upper()


def test_write_ci_outputs_creates_files_and_appends_step_summary(tmp_path, monkeypatch):
    from ghostpanel.cli.ci_output import write_ci_outputs

    step_summary = tmp_path / "step_summary.md"
    step_summary.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    write_ci_outputs(_report(), _reg(False), out_dir)

    assert (out_dir / "summary.md").is_file()
    assert (out_dir / "pr-comment.md").is_file()
    assert (out_dir / "junit.xml").is_file()

    # appended to $GITHUB_STEP_SUMMARY
    assert step_summary.read_text(encoding="utf-8").strip() != ""
