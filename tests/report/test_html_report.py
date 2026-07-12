"""Tests for the HTML leave-behind: relative media hrefs + insights section."""

from __future__ import annotations

from pathlib import Path

from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    PerturbationKind,
    StepRecord,
)

from ghostpanel.report.builder import SurvivalReportBuilder
from ghostpanel.report.html_report import render_html, write_html_report
from ghostpanel.report.insights import build_insights

RUN_ID = "test-run"


def _report(results: list[PersonaResult], personas: list[PersonaConfig]):
    return SurvivalReportBuilder().build(
        RUN_ID, "http://example.test", "Sign up", results, personas
    )


def _media_result(run_dir: Path) -> PersonaResult:
    return PersonaResult(
        persona_id="clumsy",
        outcome=PersonaOutcome.STUCK,
        failure_step=3,
        video_path=str(run_dir / "clumsy.webm"),
        audio_path=str(run_dir / "clumsy.wav"),
    )


# ---------------------------------------------------------------------------
# media hrefs
# ---------------------------------------------------------------------------
def test_written_report_links_media_by_basename(tmp_path):
    # ids not on disk in personas/ -> exercises the exact server call signature
    run_dir = tmp_path / RUN_ID
    personas = [PersonaConfig(id="clumsy", name="Clumsy")]
    report = _report([_media_result(run_dir)], personas)

    path = write_html_report(report, tmp_path)  # unchanged server signature
    html = Path(path).read_text(encoding="utf-8")

    assert 'href="clumsy.webm"' in html
    assert 'href="clumsy.wav"' in html
    # no absolute filesystem paths leak into the served page
    assert str(tmp_path) not in html


def test_media_outside_run_dir_keeps_original_path(tmp_path):
    personas = [PersonaConfig(id="clumsy", name="Clumsy")]
    elsewhere = "/somewhere/else/clumsy.webm"
    result = PersonaResult(
        persona_id="clumsy",
        outcome=PersonaOutcome.STUCK,
        video_path=elsewhere,
    )
    report = _report([result], personas)
    html = render_html(report, run_dir=tmp_path / RUN_ID)
    # a basename href would 404; the original path is kept as the safe fallback
    assert f'href="{elsewhere}"' in html


def test_render_without_run_dir_still_uses_basename():
    personas = [PersonaConfig(id="clumsy", name="Clumsy")]
    report = _report([_media_result(Path("/tmp/artifacts") / RUN_ID)], personas)
    html = render_html(report)
    assert 'href="clumsy.webm"' in html
    assert "/tmp/artifacts" not in html


# ---------------------------------------------------------------------------
# insights section
# ---------------------------------------------------------------------------
def _blurry_failure() -> tuple[list[PersonaResult], list[PersonaConfig]]:
    personas = [
        PersonaConfig(id="ai-agent", name="Agent (headless AI)", max_steps=40),
        PersonaConfig(
            id="blurry",
            name="Sam (low vision)",
            blur_sigma=3.5,
            max_steps=25,
            active_perturbations=[PerturbationKind.BLUR],
        ),
    ]
    results = [
        PersonaResult(persona_id="ai-agent", outcome=PersonaOutcome.SUCCESS),
        PersonaResult(
            persona_id="blurry",
            outcome=PersonaOutcome.STUCK,
            failure_step=7,
            failure_coords=(431, 502),
            failure_reason="repeated clicks on the decoy button",
        ),
    ]
    return results, personas


def test_insights_rendered_when_personas_passed():
    results, personas = _blurry_failure()
    report = _report(results, personas)
    html = render_html(report, personas=personas)

    assert "Ghostpanel score" in html
    assert "Agent readiness" in html
    assert "An unimpaired AI agent completed the task" in html
    # WCAG evidence table
    assert "WCAG 2.2" in html
    assert "1.4.3" in html
    assert "9.1.4.3" in html          # EN 301 549 clause
    assert "Sam (low vision)" in html
    assert "step 7" in html           # grounded evidence made it into the page


def test_precomputed_insights_are_used_verbatim():
    results, personas = _blurry_failure()
    report = _report(results, personas)
    insights = build_insights(report, personas)
    insights["summary"] = "CUSTOM-SUMMARY-SENTINEL"
    html = render_html(report, insights=insights)
    assert "CUSTOM-SUMMARY-SENTINEL" in html


def test_insights_omitted_without_personas():
    # ids that do not exist in personas/*.json -> loader fallback finds nothing
    personas = [PersonaConfig(id="nobody-on-disk", name="Nobody")]
    report = _report(
        [PersonaResult(persona_id="nobody-on-disk", outcome=PersonaOutcome.STUCK)],
        personas,
    )
    html = render_html(report)
    assert "Ghostpanel score" not in html
    assert "WCAG" not in html


# ---------------------------------------------------------------------------
# statistics sections
# ---------------------------------------------------------------------------
def _step(pid, i, action_type=ActionType.CLICK, caption="", latency=0, note=""):
    return StepRecord(
        persona_id=pid,
        step=i,
        action=Action(type=action_type, caption=caption),
        latency_ms=latency,
        note=note,
    )


def _stats_roster() -> tuple[list[PersonaResult], list[PersonaConfig]]:
    personas = [
        PersonaConfig(id="winner", name="Winner"),
        PersonaConfig(
            id="shaky",
            name="Shaky",
            tremor_sigma_px=9.0,
            active_perturbations=[PerturbationKind.TREMOR],
        ),
    ]
    results = [
        PersonaResult(
            persona_id="winner",
            outcome=PersonaOutcome.SUCCESS,
            steps=[
                _step("winner", 0, latency=120),
                _step("winner", 1, ActionType.WRITE, latency=180),
                _step("winner", 2, ActionType.SCROLL, latency=300),
            ],
            duration_s=12.0,
        ),
        PersonaResult(
            persona_id="shaky",
            outcome=PersonaOutcome.STUCK,
            steps=[
                _step("shaky", 0, caption="Click 'Buy'", latency=200),
                _step("shaky", 1, caption="Click 'Buy'", latency=0,
                      note="policy_blocked"),
            ],
            failure_step=2,
            duration_s=8.0,
        ),
    ]
    return results, personas


def test_html_renders_stats_sections():
    results, personas = _stats_roster()
    report = _report(results, personas)
    html = render_html(report, personas=personas)

    # stat tiles
    assert "Run statistics" in html
    assert "avg Holo latency" in html
    assert "p95 Holo latency" in html
    assert "policy-blocked actions" in html
    assert "200 ms" in html          # avg of 120,180,300,200 (zero excluded)
    assert "300 ms" in html          # nearest-rank p95
    # stepped survival curve (step-after path uses H/V segments)
    assert "Survival curve" in html
    assert "Stepped survival curve" in html
    assert " H" in html and " V" in html
    # per-persona table
    assert "Per-persona breakdown" in html
    assert "tremor" in html          # perturbation tag
    assert "baseline" in html        # unperturbed persona
    # actions-by-type breakdown
    assert "Actions by type" in html
    assert "click" in html and "write" in html and "scroll" in html


def test_html_degrades_without_new_insights_keys():
    # a pre-stats insights payload (old schema) must render without the new
    # sections and without crashing
    results, personas = _stats_roster()
    report = _report(results, personas)
    old_insights = {
        "ghostpanel_score": 55,
        "agent_readiness": None,
        "wcag_findings": [],
        "summary": "old-schema payload",
    }
    html = render_html(report, insights=old_insights)
    assert "Ghostpanel score" in html
    assert "old-schema payload" in html
    assert "Run statistics" not in html
    assert "Survival curve" not in html
    assert "Per-persona breakdown" not in html
    assert "Actions by type" not in html


def test_known_persona_ids_get_insights_via_disk_fallback():
    # the server calls write_html_report(report, dir) with no personas kwarg;
    # ids that exist in personas/*.json are resolved from disk
    personas = [PersonaConfig(id="grandma-72", name="Margaret, 72")]
    report = _report(
        [
            PersonaResult(
                persona_id="grandma-72",
                outcome=PersonaOutcome.STUCK,
                failure_step=4,
            )
        ],
        personas,
    )
    html = render_html(report)
    assert "Ghostpanel score" in html
