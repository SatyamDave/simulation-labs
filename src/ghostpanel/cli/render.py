"""Console rendering / progress — Agent A owns this file.

Human-facing terminal output for `sim run` (the post-run survival table) and the
live progress callback handed to ``driver.run_flow``. Plain text + ANSI only, no
external deps. ANSI is emitted only when stdout is a TTY so piped/CI output stays
clean.
"""

from __future__ import annotations

import sys
from typing import Callable

from ghostpanel_contracts import PersonaOutcome, RunReport

# --- ANSI (auto-disabled when stdout is not a terminal) --------------------
_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _green(t: str) -> str:
    return _c("32", t)


def _red(t: str) -> str:
    return _c("31", t)


def _dim(t: str) -> str:
    return _c("2", t)


def _bold(t: str) -> str:
    return _c("1", t)


def _completed(outcome: PersonaOutcome) -> bool:
    return outcome == PersonaOutcome.SUCCESS


def _rows(report: RunReport) -> list[tuple[str, str, int, bool]]:
    """(persona label, outcome, steps survived, completed) — prefer the survival
    summary; fall back to the raw PersonaResults if survival wasn't populated."""
    rows: list[tuple[str, str, int, bool]] = []
    if report.survival:
        for s in report.survival:
            label = s.persona_name or s.persona_id
            rows.append((label, s.outcome.value, s.steps_survived, s.completed))
        return rows
    for r in report.results:
        rows.append((r.persona_id, r.outcome.value, len(r.steps),
                     r.outcome == PersonaOutcome.SUCCESS))
    return rows


def print_summary(report: RunReport) -> None:
    """Print the per-persona survival table + headline completion rate."""
    rows = _rows(report)

    persona_w = max([len("PERSONA")] + [len(r[0]) for r in rows]) if rows else len("PERSONA")
    outcome_w = max([len("OUTCOME")] + [len(r[1]) for r in rows]) if rows else len("OUTCOME")

    print()
    print(_bold(f"Behavioral run {report.run_id}  ·  {report.task}"))
    print(_dim(report.target_url))
    print()

    header = f"  {'PERSONA':<{persona_w}}  {'OUTCOME':<{outcome_w}}  {'STEPS':>5}  {'':<3}"
    print(_bold(header))
    print(_dim("  " + "-" * (len(header) - 2)))
    for label, outcome, steps, completed in rows:
        mark = _green("✓") if completed else _red("✗")
        outcome_disp = _green(outcome) if completed else _red(outcome)
        # pad on the raw (uncolored) text so alignment survives ANSI codes
        pad = " " * max(0, outcome_w - len(outcome))
        print(f"  {label:<{persona_w}}  {outcome_disp}{pad}  {steps:>5}  {mark}")

    rate = report.completion_rate
    n = len(rows)
    passed = sum(1 for r in rows if r[3])
    pct = f"{rate * 100:.0f}%"
    line = f"Completion rate: {pct}  ({passed}/{n} personas completed)"
    print()
    print(_bold(_green(line) if rate >= 0.5 else _bold(_red(line))))
    print()


def make_progress_printer() -> Callable[[dict], None]:
    """Return an `on_event(dict)` callback for driver.run_flow that prints a live,
    one-line-per-event progress view. Tolerant of any RunEvent shape."""

    def on_event(event: dict) -> None:
        if not isinstance(event, dict):
            return
        kind = str(event.get("event", ""))
        persona = event.get("persona_id") or ""

        if kind == "run_started":
            personas = event.get("personas") or []
            print(_dim(f"→ run started ({len(personas)} personas)"))
        elif kind == "persona_started":
            print(_dim(f"  [{persona}] started"))
        elif kind == "step":
            step = event.get("step")
            caption = event.get("caption") or "(no caption)"
            prefix = f"  [{persona}] step {step}: " if step is not None else f"  [{persona}] "
            print(f"{prefix}{caption}")
        elif kind == "persona_finished":
            outcome = event.get("outcome", "?")
            steps = event.get("steps_survived")
            done = outcome == PersonaOutcome.SUCCESS.value
            mark = _green("✓") if done else _red("✗")
            tail = f" ({steps} steps)" if steps is not None else ""
            print(f"  [{persona}] {mark} {outcome}{tail}")
        elif kind == "run_finished":
            rate = event.get("completion_rate")
            if isinstance(rate, (int, float)):
                print(_dim(f"← run finished (completion {rate * 100:.0f}%)"))
            else:
                print(_dim("← run finished"))
        else:
            # Unknown shape — degrade gracefully rather than raise.
            caption = event.get("caption")
            if caption:
                who = f"[{persona}] " if persona else ""
                print(f"  {who}{caption}")

    return on_event
