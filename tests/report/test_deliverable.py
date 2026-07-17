"""Tests for the hand-deliverable client report (report/deliverable.py).

The deliverable is the product in the manual-audit phase: a single self-contained
HTML file, findings-first, CRO-framed. These tests pin the load-bearing promises:
  * it leads with written findings derived from the run,
  * it is self-contained (no external asset refs; only relative .webm/.wav),
  * it uses behavioral-segment framing and NEVER accessibility/impairment framing,
  * it renders the canonical fixture and degrades sensibly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    PerturbationKind,
    RunReport,
    StepRecord,
    Viewport,
)

from ghostpanel.report.builder import SurvivalReportBuilder
from ghostpanel.report.deliverable import (
    _safe_persona_name,
    _segment,
    build_findings,
    render_deliverable,
    write_deliverable_report,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "run.json"

# Words that must never appear as framing in a CRO deliverable. (We allow them
# only inside relative media filenames the fixture happens to carry, which are
# links, not copy — those are excluded in the body-copy assertions below.)
_IMPAIRMENT = ["accessib", "impair", "disab", "wcag", "low vision",
               "hand tremor", "colorblind", "deuteran", "screen reader"]


def _report(results, personas) -> RunReport:
    return SurvivalReportBuilder().build(
        "cro-run", "http://shop.test/checkout", "Check out", results, personas
    )


def _current_roster():
    """The current CRO persona roster (names ARE the segment names)."""
    personas = [
        PersonaConfig(id="fluent", name="Fluent"),
        PersonaConfig(
            id="misclick-prone", name="Misclick-prone", tremor_sigma_px=14,
            active_perturbations=[PerturbationKind.TREMOR],
        ),
        PersonaConfig(
            id="rushed", name="Rushed", max_steps=8, deadline_s=30,
            active_perturbations=[PerturbationKind.IMPATIENCE],
        ),
        PersonaConfig(
            id="mobile-thumb", name="Mobile-thumb",
            viewport=Viewport(width=390, height=844),
            active_perturbations=[PerturbationKind.SMALL_VIEWPORT],
        ),
    ]
    results = [
        PersonaResult(
            persona_id="fluent", outcome=PersonaOutcome.SUCCESS,
            steps=[
                StepRecord(persona_id="fluent", step=0,
                           action=Action(type=ActionType.CLICK, x=100, y=200,
                                         caption="Click Sign up")),
                StepRecord(persona_id="fluent", step=1,
                           action=Action(type=ActionType.WRITE, x=120, y=260,
                                         caption="Type email")),
            ],
            duration_s=11.0,
        ),
        PersonaResult(
            persona_id="misclick-prone", outcome=PersonaOutcome.STUCK,
            failure_step=5, failure_coords=(640, 300),
            failure_reason="Clicked the 'Apply promo' link three times by mistake",
            duration_s=22.0, video_path="artifacts/cro-run/misclick-prone.webm",
        ),
        PersonaResult(
            persona_id="rushed", outcome=PersonaOutcome.TIME_BUDGET,
            failure_step=4, failure_coords=(655, 315), duration_s=30.0,
        ),
        PersonaResult(
            persona_id="mobile-thumb", outcome=PersonaOutcome.STEP_BUDGET,
            failure_step=8, failure_coords=(200, 700), duration_s=18.0,
        ),
    ]
    return results, personas


# ---------------------------------------------------------------------------
# segment classification
# ---------------------------------------------------------------------------
def test_segment_from_perturbations_and_names():
    assert _segment("misclick-prone", "Misclick-prone", []) == "Misclick-prone"
    assert _segment("mobile-thumb", "Mobile-thumb", []) == "Mobile-thumb"
    assert _segment("rushed", "Rushed", []) == "Rushed"
    assert _segment("first-timer", "First-timer", []) == "First-timer"
    assert _segment("fluent", "Fluent", []) == "Fluent"
    # perturbation-driven (name gives nothing away)
    assert _segment("p1", "Persona One", ["tremor"]) == "Misclick-prone"
    assert _segment("p2", "Persona Two", ["small_viewport"]) == "Mobile-thumb"
    assert _segment("p3", "Persona Three", ["impatience"]) == "Rushed"
    assert _segment("p4", "Persona Four", ["blur"]) == "First-timer"
    # legacy fixture ids reframe cleanly
    assert _segment("ai-agent", "Agent (headless AI)", []) == "AI Agent"
    assert _segment("low-vision", "Sam (low vision)", []) == "First-timer"
    assert _segment("tremor", "Dev (hand tremor)", []) == "Misclick-prone"
    assert _segment("power-user", "Alex (power user)", []) == "Fluent"


def test_safe_persona_name_scrubs_impairment_wording():
    # equal to segment or carrying legacy impairment wording -> suppressed
    assert _safe_persona_name("Fluent", "Fluent") == ""
    assert _safe_persona_name("Sam (low vision)", "First-timer") == ""
    assert _safe_persona_name("Dev (hand tremor)", "Misclick-prone") == ""
    # a clean, distinct human label survives
    assert _safe_persona_name("Alex", "Fluent") == "Alex"


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------
def test_findings_lead_and_are_cro_framed():
    results, personas = _current_roster()
    report = _report(results, personas)
    html = render_deliverable(report, personas=personas)

    # findings section leads (before the heatmap/survival evidence)
    fi = html.index("Findings")
    assert fi < html.index("Abandonment heatmap")
    assert fi < html.index("Survival curve")

    # a cluster finding names the segments that died together + the control
    assert "Apply promo" in html          # label lifted from the trace
    assert "Misclick-prone" in html
    # a contrast finding: the flow works for the confident user
    assert "comprehension gaps" in html
    # segments framed as CRO segments, no impairment framing anywhere in copy
    low = html.lower()
    for bad in _IMPAIRMENT:
        assert bad not in low, f"impairment framing leaked: {bad!r}"


def test_build_findings_clean_sweep_when_all_succeed():
    personas = [PersonaConfig(id="fluent", name="Fluent")]
    report = _report(
        [PersonaResult(persona_id="fluent", outcome=PersonaOutcome.SUCCESS)],
        personas,
    )
    html = render_deliverable(report, personas=personas)
    assert "Clean sweep" in html
    assert "100%" in html


def test_build_findings_always_returns_at_least_one():
    personas = [PersonaConfig(id="rushed", name="Rushed")]
    report = _report(
        [PersonaResult(persona_id="rushed", outcome=PersonaOutcome.STUCK,
                       failure_step=2)],
        personas,
    )
    from ghostpanel.report.deliverable import _build_roster
    roster = _build_roster(report, {}, None)
    findings = build_findings(roster, {}, 1280, 800)
    assert len(findings) >= 1
    assert all("headline" in f and "evidence" in f and "impact" in f
               for f in findings)


# ---------------------------------------------------------------------------
# self-containment (the core promise of a hand-deliverable file)
# ---------------------------------------------------------------------------
def _assert_self_contained(html: str):
    # no external asset references of any kind
    assert not re.search(r'(?:src|href)\s*=\s*"https?://', html)
    assert "url(http" not in html
    assert "@import" not in html
    assert "<link " not in html
    assert "<script" not in html
    # no remote fonts (Space Grotesk is only *named*, with a system fallback)
    assert "fonts.googleapis" not in html
    assert "fonts.gstatic" not in html
    assert "@font-face" not in html
    assert "Space Grotesk" in html


def test_render_is_self_contained():
    results, personas = _current_roster()
    html = render_deliverable(_report(results, personas), personas=personas)
    _assert_self_contained(html)


def test_media_linked_relatively_by_basename(tmp_path):
    results, personas = _current_roster()
    report = _report(results, personas)
    run_dir = tmp_path / report.run_id
    html = render_deliverable(report, personas=personas, run_dir=run_dir)
    assert 'href="misclick-prone.webm"' in html
    # only relative media links, never an absolute filesystem path
    assert str(tmp_path) not in html
    for m in re.findall(r'href="([^"]+\.(?:webm|wav))"', html):
        assert not m.startswith("http") and not m.startswith("/")


# ---------------------------------------------------------------------------
# brand + written-to-disk
# ---------------------------------------------------------------------------
def test_brand_tokens_present():
    results, personas = _current_roster()
    html = render_deliverable(_report(results, personas), personas=personas)
    assert "#0B0D11" in html          # bg
    assert "#4C8DFF" in html          # blue accent
    assert "#39D0E0" in html          # cyan accent
    assert "Simulation Labs" in html


def test_write_deliverable_report_writes_report_html(tmp_path):
    results, personas = _current_roster()
    report = _report(results, personas)
    path = write_deliverable_report(report, tmp_path, personas=personas)
    p = Path(path)
    assert p.name == "report.html"
    assert p.parent.name == report.run_id
    _assert_self_contained(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# canonical fixture renders end-to-end
# ---------------------------------------------------------------------------
def test_renders_canonical_fixture_cleanly(tmp_path):
    data = {k: v for k, v in json.loads(FIXTURE.read_text()).items()
            if not k.startswith("_")}
    report = RunReport.model_validate(data)
    path = write_deliverable_report(report, tmp_path)
    html = Path(path).read_text(encoding="utf-8")

    _assert_self_contained(html)
    assert "Findings" in html
    assert "33%" in html                       # completion_rate 0.333
    assert "Abandonment heatmap" in html
    # legacy impairment framing from the fixture data is scrubbed from copy
    low_body = re.sub(r'href="[^"]+"', "", html).lower()  # drop media hrefs
    for bad in _IMPAIRMENT:
        assert bad not in low_body, f"impairment framing leaked: {bad!r}"
    # current segment framing surfaces instead
    assert "First-timer" in html and "Misclick-prone" in html
