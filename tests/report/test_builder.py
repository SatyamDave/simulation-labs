"""SurvivalReportBuilder: survival math, ERROR exclusion, valid RunReport,
plus the HTML artifact rendering."""

from datetime import datetime

from ghostpanel_contracts import (
    CONTRACT_VERSION,
    PersonaOutcome,
    PersonaResult,
    ReportBuilder,
    RunReport,
)

from ghostpanel.report.builder import SurvivalReportBuilder
from ghostpanel.report.html_report import render_html, write_html

RUN_ARGS = dict(
    run_id="demo-run-0001",
    target_url="http://localhost:8137/fixtures/hostile_form.html",
    task="Create an account and start the free trial.",
)


def test_satisfies_report_builder_protocol():
    assert isinstance(SurvivalReportBuilder(), ReportBuilder)


def test_one_survival_point_per_result(fixture_results, fixture_personas):
    report = SurvivalReportBuilder().build(
        **RUN_ARGS, results=fixture_results, personas=fixture_personas
    )
    assert len(report.survival) == len(fixture_results)
    by_id = {s.persona_id: s for s in report.survival}
    # grandma: 4 recorded steps, stuck, name looked up from personas
    grandma = by_id["grandma-72"]
    assert grandma.steps_survived == 4
    assert grandma.completed is False
    assert grandma.persona_name == "Margaret, 72"
    # power user: success
    assert by_id["power-user"].completed is True


def test_completion_rate_excludes_error(fixture_results, fixture_personas):
    error_result = PersonaResult(persona_id="crash-dummy", outcome=PersonaOutcome.ERROR)
    report = SurvivalReportBuilder().build(
        **RUN_ARGS, results=fixture_results + [error_result], personas=fixture_personas
    )
    # fixture: 1 success + 1 stuck; the ERROR persona is excluded from the math
    assert report.completion_rate == 0.5
    # ...but still gets a survival point (visible, marked as infra error)
    assert len(report.survival) == 3


def test_completion_rate_handles_zero_division(fixture_personas):
    builder = SurvivalReportBuilder()
    empty = builder.build(**RUN_ARGS, results=[], personas=fixture_personas)
    assert empty.completion_rate == 0.0
    all_error = builder.build(
        **RUN_ARGS,
        results=[PersonaResult(persona_id="crash-dummy", outcome=PersonaOutcome.ERROR)],
        personas=fixture_personas,
    )
    assert all_error.completion_rate == 0.0


def test_steps_survived_falls_back_to_failure_step(fixture_personas):
    result = PersonaResult(
        persona_id="grandma-72",
        outcome=PersonaOutcome.STUCK,
        steps=[],
        failure_step=5,
    )
    report = SurvivalReportBuilder().build(
        **RUN_ARGS, results=[result], personas=fixture_personas
    )
    assert report.survival[0].steps_survived == 5


def test_report_is_valid_and_stamped(fixture_results, fixture_personas):
    report = SurvivalReportBuilder().build(
        **RUN_ARGS, results=fixture_results, personas=fixture_personas
    )
    # round-trips through the frozen contract
    assert RunReport.model_validate_json(report.model_dump_json()).run_id == "demo-run-0001"
    assert report.contract_version == CONTRACT_VERSION
    datetime.fromisoformat(report.generated_at)  # ISO8601 or raises
    # heatmap came from heatmap.py: grandma abandoned at (300, 145)
    assert any(p.persona_id == "grandma-72" and (p.x, p.y) == (300, 145)
               for p in report.heatmap_points)


def test_render_html_is_standalone_and_grounded(fixture_report):
    html = render_html(fixture_report)
    assert html.startswith("<!doctype html>")
    assert "33%" in html                       # headline completion rate
    assert "Margaret, 72" in html              # survival table
    assert "<svg" in html                      # inline SVG bar chart
    assert "grandma-72.wav" in html            # artifact link
    assert "big blue button" in html           # exit-interview transcript


def test_write_html_writes_under_run_id(fixture_report, tmp_path):
    out = write_html(fixture_report, tmp_path)
    assert out == tmp_path / "demo-run-0001" / "report.html"
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
