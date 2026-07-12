"""Tests for SurvivalReportBuilder, fed the PersonaResults from fixtures/run.json."""

from __future__ import annotations

import json
from pathlib import Path

from ghostpanel_contracts import (
    CONTRACT_VERSION,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    ReportBuilder,
    RunReport,
)

from ghostpanel.report.builder import SurvivalReportBuilder

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "run.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _results() -> list[PersonaResult]:
    data = _load_fixture()
    return [PersonaResult.model_validate(r) for r in data["results"]]


def _personas() -> list[PersonaConfig]:
    data = _load_fixture()
    return [
        PersonaConfig(id=s["persona_id"], name=s["persona_name"])
        for s in data["survival"]
    ]


def test_builder_satisfies_protocol():
    assert isinstance(SurvivalReportBuilder(), ReportBuilder)


def test_build_basic_report():
    results = _results()
    personas = _personas()
    report = SurvivalReportBuilder().build(
        run_id="test-run",
        target_url="http://example.test",
        task="Sign up",
        results=results,
        personas=personas,
    )

    assert isinstance(report, RunReport)
    assert report.run_id == "test-run"
    assert report.contract_version == CONTRACT_VERSION
    assert report.generated_at  # stamped, ISO8601
    # ISO8601 parses
    from datetime import datetime

    datetime.fromisoformat(report.generated_at)

    # one SurvivalPoint per result
    assert len(report.survival) == len(results)

    # names looked up from personas
    by_id = {s.persona_id: s for s in report.survival}
    assert by_id["grandma-72"].persona_name == "Margaret, 72"
    assert by_id["power-user"].persona_name == "Alex (power user)"

    # completed flag
    assert by_id["power-user"].completed is True
    assert by_id["grandma-72"].completed is False

    # fixture: 1 success (power-user) of 2 non-error personas
    assert report.completion_rate == 0.5


def test_error_excluded_from_completion_rate():
    results = _results()
    # add an infra ERROR result: should NOT count against the denominator
    results.append(
        PersonaResult(persona_id="crashy", outcome=PersonaOutcome.ERROR)
    )
    personas = _personas() + [PersonaConfig(id="crashy", name="Crashy")]

    report = SurvivalReportBuilder().build(
        run_id="test-run",
        target_url="http://example.test",
        task="Sign up",
        results=results,
        personas=personas,
    )

    # one SurvivalPoint per result, incl. the error one
    assert len(report.survival) == 3
    # denominator excludes ERROR: 1 success / 2 non-error = 0.5 (not /3)
    assert report.completion_rate == 0.5


def test_steps_survived_uses_failure_step_or_len():
    results = _results()
    report = SurvivalReportBuilder().build(
        "r", "u", "t", results, _personas()
    )
    by_id = {s.persona_id: s for s in report.survival}
    # grandma-72 has failure_step=4 in the fixture
    assert by_id["grandma-72"].steps_survived == 4
    # power-user succeeded, no failure_step, no steps -> 0
    assert by_id["power-user"].steps_survived == 0
