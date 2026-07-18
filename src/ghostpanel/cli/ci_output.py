"""CI-native output formatters — Agent C owns this file.

Turns a RunReport + RegressionResult into the artifacts CI understands: a console
table, a GitHub step summary, a PR comment, and JUnit XML. Signatures are FROZEN
(main.py and render.py import from here). No external dependencies.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape
from xml.sax.saxutils import quoteattr as _xml_quoteattr

from ghostpanel_contracts import PersonaOutcome, RunReport

from .regression import (
    BEHAVIORAL_REGRESSION,
    FUNCTIONAL_FAIL,
    RegressionResult,
)

# Stable marker so the GitHub Action can find & update its own PR comment
# instead of posting a new one every run.
PR_COMMENT_MARKER = "<!-- simulationlabs-gate -->"

_CHECK = "✓"  # ✓
_CROSS = "✗"  # ✗

# ANSI
_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _use_color() -> bool:
    """True only when it is safe to emit ANSI (real TTY, NO_COLOR unset)."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _pct(fraction: float | None) -> str:
    if fraction is None:
        return "n/a"
    return f"{fraction * 100:.0f}%"


def _outcome_str(outcome: PersonaOutcome | str) -> str:
    return outcome.value if isinstance(outcome, PersonaOutcome) else str(outcome)


def _threshold_display(reg: RegressionResult) -> str:
    """Human phrase for the effective bar, e.g. '80% (absolute)' or
    '75% (last-passing baseline)'."""
    if reg.fail_under == "last-passing":
        if reg.completion_baseline is None:
            return "last-passing (no baseline yet — first run seeds it)"
        return f"{_pct(reg.threshold)} (last-passing baseline)"
    return f"{_pct(reg.threshold)} (absolute bar)"


def _completions(report: RunReport) -> tuple[int, int]:
    """(#completed, #counted) — ERROR outcomes are excluded from the denominator."""
    counted = [s for s in report.survival if s.outcome != PersonaOutcome.ERROR]
    completed = sum(1 for s in counted if s.completed)
    return completed, len(counted)


def _failure_hotspots(report: RunReport, limit: int = 5) -> list[tuple[tuple[int, int], int]]:
    """Most common (x, y) abandonment coordinates across personas."""
    coords = Counter(
        r.failure_coords for r in report.results if r.failure_coords is not None
    )
    return coords.most_common(limit)


# ---------------------------------------------------------------------------
# console table
# ---------------------------------------------------------------------------
def summary_table(report: RunReport) -> str:
    """Plain/ANSI per-persona survival table for the console (no external deps)."""
    color = _use_color()

    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    rows = report.survival
    name_hdr, outcome_hdr, steps_hdr, done_hdr = "PERSONA", "OUTCOME", "STEPS", "DONE"

    name_w = max([len(name_hdr)] + [len(s.persona_name or s.persona_id) for s in rows] or [0])
    outcome_w = max([len(outcome_hdr)] + [len(_outcome_str(s.outcome)) for s in rows] or [0])
    steps_w = max([len(steps_hdr)] + [len(str(s.steps_survived)) for s in rows] or [0])

    completed, counted = _completions(report)
    rate = report.completion_rate
    verdict_word = f"{completed}/{counted} personas completed"
    header = paint(
        f"Behavioral run — completion {_pct(rate)}  ({verdict_word})", _BOLD
    )

    lines = [header, ""]
    head_line = (
        f"  {name_hdr:<{name_w}}  {outcome_hdr:<{outcome_w}}  "
        f"{steps_hdr:>{steps_w}}  {done_hdr}"
    )
    lines.append(paint(head_line, _DIM))
    lines.append(paint("  " + "-" * (len(head_line) - 2), _DIM))

    for s in rows:
        name = s.persona_name or s.persona_id
        outcome = _outcome_str(s.outcome)
        if s.completed:
            mark = paint(_CHECK, _GREEN)
        else:
            mark = paint(_CROSS, _RED)
        line = (
            f"  {name:<{name_w}}  {outcome:<{outcome_w}}  "
            f"{s.steps_survived:>{steps_w}}  {mark}"
        )
        lines.append(line)

    if not rows:
        lines.append(paint("  (no personas in this run)", _DIM))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# markdown shared pieces
# ---------------------------------------------------------------------------
def _verdict_line(reg: RegressionResult) -> str:
    """Verdict badge. ``passed`` is authoritative; ``verdict`` only refines the
    FAIL label to distinguish a broken flow (functional) from one that works but
    leaks degraded users (behavioral)."""
    if reg.passed:
        return "**✅ PASS**"
    if reg.verdict == FUNCTIONAL_FAIL:
        return "**🛑 FUNCTIONAL FAIL** (flow broken)"
    if reg.verdict == BEHAVIORAL_REGRESSION:
        return "**❌ BEHAVIORAL REGRESSION**"
    return "**❌ FAIL**"


def _completion_delta_line(reg: RegressionResult) -> str:
    now = _pct(reg.completion_now)
    if reg.completion_baseline is None:
        return f"Completion: **{now}** (no baseline)"
    base = _pct(reg.completion_baseline)
    delta = (reg.completion_now - reg.completion_baseline) * 100
    arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
    return f"Completion: **{now}** vs baseline {base} ({arrow} {delta:+.0f} pts)"


def _regressed_table_md(reg: RegressionResult) -> list[str]:
    if not reg.regressed_personas:
        return []
    lines = [
        "",
        f"**Regressed personas ({len(reg.regressed_personas)})** — completed before, fail now:",
        "",
        "| Persona | Was | Now | Steps (was → now) |",
        "| --- | --- | --- | --- |",
    ]
    for d in reg.regressed_personas:
        name = d.persona_name or d.persona_id
        was = _CHECK if d.was else _CROSS
        now = _CHECK if d.now else _CROSS
        lines.append(f"| {name} | {was} | {now} | {d.steps_was} → {d.steps_now} |")
    return lines


def _dead_zones_md(report: RunReport, reg: RegressionResult) -> list[str]:
    hotspots = _failure_hotspots(report)
    lines: list[str] = []
    if hotspots:
        lines += ["", "**Where users died** (top abandonment pixels):", ""]
        for (x, y), n in hotspots:
            plural = "persona" if n == 1 else "personas"
            lines.append(f"- `({x}, {y})` — {n} {plural}")
    if reg.new_dead_zones:
        lines += ["", "**New dead zones** (absent from baseline):", ""]
        for (x, y) in reg.new_dead_zones:
            lines.append(f"- `({x}, {y})`")
    return lines


# ---------------------------------------------------------------------------
# GitHub step summary
# ---------------------------------------------------------------------------
def step_summary_md(report: RunReport, reg: RegressionResult) -> str:
    """Markdown for $GITHUB_STEP_SUMMARY (verdict + completion + regressions)."""
    completed, counted = _completions(report)
    lines: list[str] = [
        "## Simulation Labs — behavioral gate",
        "",
        f"{_verdict_line(reg)} — {reg.reason}",
        "",
        f"- {_completion_delta_line(reg)}",
        f"- Bar: {_threshold_display(reg)}",
        f"- Personas completed: **{completed}/{counted}**",
        f"- Target: `{report.target_url}`",
        f"- Task: {report.task}",
    ]
    lines += _regressed_table_md(reg)
    lines += _dead_zones_md(report, reg)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PR comment
# ---------------------------------------------------------------------------
def pr_comment_md(
    report: RunReport,
    reg: RegressionResult,
    *,
    report_url: str | None = None,
) -> str:
    """Markdown PR comment: verdict, completion delta, where users died."""
    completed, counted = _completions(report)
    lines: list[str] = [
        PR_COMMENT_MARKER,
        f"### {_verdict_line(reg)} · Simulation Labs behavioral gate",
        "",
        reg.reason,
        "",
        f"- {_completion_delta_line(reg)}  ({completed}/{counted} personas)",
        f"- Bar: {_threshold_display(reg)}",
    ]
    if report_url:
        lines.append(f"- [Full report, video receipts & exit interviews]({report_url})")

    lines += _regressed_table_md(reg)

    # Keep the PR comment concise: only the single worst hotspot inline.
    hotspots = _failure_hotspots(report, limit=1)
    if hotspots:
        (x, y), n = hotspots[0]
        plural = "persona" if n == 1 else "personas"
        lines += ["", f"Biggest drop-off: `({x}, {y})` ({n} {plural} abandoned there)."]

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JUnit XML
# ---------------------------------------------------------------------------
def junit_xml(report: RunReport, reg: RegressionResult) -> str:
    """JUnit XML (one testcase per persona/flow) for the checks tab."""
    results_by_id = {r.persona_id: r for r in report.results}
    classname = f"{report.task} ({report.target_url})"

    failures = 0
    errors = 0
    cases: list[str] = []

    for s in report.survival:
        name = s.persona_name or s.persona_id
        result = results_by_id.get(s.persona_id)
        duration = result.duration_s if result else 0.0
        reason = (result.failure_reason if result else "") or _outcome_str(s.outcome)

        case_attrs = (
            f"name={_xml_quoteattr(name)} "
            f"classname={_xml_quoteattr(classname)} "
            f"time={_xml_quoteattr(f'{duration:.3f}')}"
        )

        if s.completed:
            cases.append(f"    <testcase {case_attrs}/>")
            continue

        if s.outcome == PersonaOutcome.ERROR:
            # Infra failure, not a real abandonment — model as an <error>.
            errors += 1
            tag, msg = "error", f"infra error: {reason}"
        else:
            failures += 1
            tag, msg = "failure", reason

        body = _xml_escape(
            f"Outcome: {_outcome_str(s.outcome)} after {s.steps_survived} steps.\n{reason}"
        )
        cases.append(
            f"    <testcase {case_attrs}>\n"
            f"      <{tag} type={_xml_quoteattr(_outcome_str(s.outcome))} "
            f"message={_xml_quoteattr(msg)}>{body}</{tag}>\n"
            f"    </testcase>"
        )

    suite_name = "simulationlabs.gate"
    suite_attrs = (
        f"name={_xml_quoteattr(suite_name)} "
        f"tests={_xml_quoteattr(str(len(report.survival)))} "
        f"failures={_xml_quoteattr(str(failures))} "
        f"errors={_xml_quoteattr(str(errors))}"
    )
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<testsuites>",
        f"  <testsuite {suite_attrs}>",
        *cases,
        "  </testsuite>",
        "</testsuites>",
    ]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# write everything
# ---------------------------------------------------------------------------
def write_ci_outputs(report: RunReport, reg: RegressionResult, out_dir: Path) -> None:
    """Write {summary.md, pr-comment.md, junit.xml} under out_dir; also append
    summary.md to $GITHUB_STEP_SUMMARY when that env var is set."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = step_summary_md(report, reg)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    (out_dir / "pr-comment.md").write_text(
        pr_comment_md(report, reg), encoding="utf-8"
    )
    (out_dir / "junit.xml").write_text(junit_xml(report, reg), encoding="utf-8")

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as fh:
            fh.write(summary)
            if not summary.endswith("\n"):
                fh.write("\n")


__all__ = [
    "summary_table",
    "step_summary_md",
    "pr_comment_md",
    "junit_xml",
    "write_ci_outputs",
    "PR_COMMENT_MARKER",
]
