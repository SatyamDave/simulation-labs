"""Console rendering / progress — Agent A owns this file.

Human-facing terminal output for `sim run`/`sim try` (the post-run survival
table) and the live progress callback handed to ``driver.run_flow``. Plain text +
ANSI only, no external deps. ANSI is emitted only when stdout is a TTY and
``NO_COLOR`` is unset, so piped/CI output stays clean.

Colour carries meaning, not decoration:
  green  — the flow completed (control users, your ceiling)
  amber  — a real user *gave up* (step/time budget) — the behavioural signal
  red    — the flow was *stuck* or errored (functional/infra failure)
Each degraded agent that abandons is annotated with the exact pixel it walked
away at — the whole product promise, surfaced in the terminal.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

from ghostpanel_contracts import PersonaOutcome, RunReport

# --- ANSI (auto-disabled when stdout is not a terminal or NO_COLOR is set) ---
_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _green(t: str) -> str:
    return _c("32", t)


def _red(t: str) -> str:
    return _c("31", t)


def _amber(t: str) -> str:
    return _c("33", t)


def _dim(t: str) -> str:
    return _c("2", t)


def _bold(t: str) -> str:
    return _c("1", t)


# Outcomes that mean "a real user gave up here" (behavioural signal → amber) as
# opposed to "the flow was stuck / errored" (functional/infra failure → red).
_BEHAVIORAL_GIVEUP = {PersonaOutcome.STEP_BUDGET.value, PersonaOutcome.TIME_BUDGET.value}

# Stable, distinct hues used ONLY to tint each agent's [label] in the live stream
# so five concurrent agents are visually separable. Status marks stay green/amber/
# red so colour still means outcome, never identity.
_AGENT_HUES = ["36", "35", "94", "96", "33", "34"]


def _paint_outcome(outcome: str, completed: bool) -> str:
    if completed:
        return _green(outcome)
    if outcome in _BEHAVIORAL_GIVEUP:
        return _amber(outcome)
    return _red(outcome)


def _mark(completed: bool, outcome: str) -> str:
    if completed:
        return _green("✓")
    if outcome in _BEHAVIORAL_GIVEUP:
        return _amber("✗")
    return _red("✗")


def _completed(outcome: PersonaOutcome) -> bool:
    return outcome == PersonaOutcome.SUCCESS


def _rows(report: RunReport) -> list[tuple[str, str, int, bool, Optional[tuple[int, int]]]]:
    """(persona label, outcome, steps survived, completed, failure_coords) — prefer
    the survival summary; fall back to the raw PersonaResults if survival wasn't
    populated. ``failure_coords`` is the viewport pixel the agent abandoned at (or
    None if it completed / no coordinate was recorded)."""
    # failure_coords lives on PersonaResult, NOT on the survival summary — look it
    # up by persona_id so the abandonment pixel actually reaches the table.
    coords_by_id = {r.persona_id: r.failure_coords for r in report.results}
    rows: list[tuple[str, str, int, bool, Optional[tuple[int, int]]]] = []
    if report.survival:
        for s in report.survival:
            label = s.persona_name or s.persona_id
            rows.append(
                (label, s.outcome.value, s.steps_survived, s.completed,
                 coords_by_id.get(s.persona_id))
            )
        return rows
    for r in report.results:
        rows.append((r.persona_id, r.outcome.value, len(r.steps),
                     r.outcome == PersonaOutcome.SUCCESS, r.failure_coords))
    return rows


def print_summary(report: RunReport, *, header: bool = True) -> None:
    """Print the per-persona survival table + headline completion rate. Failing
    agents are annotated with the exact pixel they abandoned at, when known. Set
    ``header=False`` to omit the run-id/task/URL banner (the compact summary view)."""
    rows = _rows(report)

    persona_w = max([len("PERSONA")] + [len(r[0]) for r in rows]) if rows else len("PERSONA")
    outcome_w = max([len("OUTCOME")] + [len(r[1]) for r in rows]) if rows else len("OUTCOME")
    steps_w = max([len("STEPS")] + [len(str(r[2])) for r in rows]) if rows else len("STEPS")

    print()
    if header:
        print(_bold(f"Behavioral run {report.run_id}  ·  {report.task}"))
        print(_dim(report.target_url))
        print()

    header = f"  {'PERSONA':<{persona_w}}  {'OUTCOME':<{outcome_w}}  {'STEPS':>{steps_w}}"
    print(_bold(header))
    print(_dim("  " + "-" * (len(header) - 2)))
    for label, outcome, steps, completed, coords in rows:
        mark = _mark(completed, outcome)
        outcome_disp = _paint_outcome(outcome, completed)
        # pad on the raw (uncolored) text so alignment survives ANSI codes
        pad = " " * max(0, outcome_w - len(outcome))
        line = f"  {label:<{persona_w}}  {outcome_disp}{pad}  {steps:>{steps_w}}  {mark}"
        if not completed and coords is not None:
            x, y = coords
            line += _dim(f"  ← gave up at ({x}, {y})")
        print(line)

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
    one-line-per-event progress view. Each agent's [label] gets a stable hue so the
    five concurrent streams stay legible; failures show their outcome colour and,
    when the event carries it, the pixel/reason they abandoned at. Tolerant of any
    RunEvent shape."""
    hue_of: dict[str, str] = {}

    def _label(persona: str) -> str:
        if not persona:
            return ""
        if persona not in hue_of:
            hue_of[persona] = _AGENT_HUES[len(hue_of) % len(_AGENT_HUES)]
        return _c(hue_of[persona], f"[{persona}]")

    def on_event(event: dict) -> None:
        if not isinstance(event, dict):
            return
        kind = str(event.get("event", ""))
        persona = event.get("persona_id") or ""

        if kind == "run_started":
            personas = event.get("personas") or []
            print(_dim(f"→ run started ({len(personas)} agents, concurrently)"))
        elif kind == "persona_started":
            print(_dim(f"  {_label(persona)} started"))
        elif kind == "step":
            step = event.get("step")
            caption = event.get("caption") or "(no caption)"
            prefix = f"  {_label(persona)} step {step}: " if step is not None else f"  {_label(persona)} "
            print(f"{prefix}{_dim(caption)}")
        elif kind == "persona_finished":
            outcome = str(event.get("outcome", "?"))
            steps = event.get("steps_survived")
            done = outcome == PersonaOutcome.SUCCESS.value
            mark = _mark(done, outcome)
            tail = f" ({steps} steps)" if steps is not None else ""
            line = f"  {_label(persona)} {mark} {_paint_outcome(outcome, done)}{tail}"
            coords = event.get("failure_coords")
            reason = event.get("failure_reason")
            if not done and coords and isinstance(coords, (list, tuple)) and len(coords) == 2:
                line += _dim(f"  ← gave up at ({coords[0]}, {coords[1]})")
            elif not done and reason:
                line += _dim(f"  — {reason}")
            print(line)
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
                who = f"{_label(persona)} " if persona else ""
                print(f"  {who}{caption}")

    return on_event
