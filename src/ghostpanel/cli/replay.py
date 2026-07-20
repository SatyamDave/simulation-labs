"""Keyless-demo replay — Agent A owns this file.

`sim try` with no model key REPLAYS real, previously-captured runs of the bundled
demo flow (see recorded_demo.py) instead of dead-ending on a missing key. This is
the honest asciinema pattern: every number, caption and outcome comes from a
genuine recorded run, replayed deterministically through the SAME renderer a live
run uses — so no model is called, no key/browser/network is needed, and a stranger
sees the real result in seconds. A live run (a key set, or `sim try --live`)
always overrides this.

The hero is a two-run regression story: RUN 1 the working form (the swarm — degraded
segments included — completes it, gate PASS); RUN 2 the SAME swarm on a build where a
regression broke the flow (gate FAIL, merge blocked). Both are real recorded runs.
If only the working cassette ships, replay degrades to a single run.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

from ghostpanel_contracts import RunReport

from . import render


def _load(attr: str) -> Optional[RunReport]:
    try:
        from . import recorded_demo

        raw = getattr(recorded_demo, attr, None)
        if not raw:
            return None
        return RunReport.model_validate(json.loads(raw))
    except Exception:  # noqa: BLE001 — a missing/corrupt cassette must not crash `sim try`
        return None


def load_cassette() -> Optional[RunReport]:
    """The working-form run (gate PASS half of the hero)."""
    return _load("CASSETTE_JSON")


def load_broken_cassette() -> Optional[RunReport]:
    """The regressed-build run (gate FAIL half), or None if not shipped."""
    return _load("CASSETTE_BROKEN_JSON")


def _provenance() -> dict:
    try:
        from . import recorded_demo

        return dict(recorded_demo.PROVENANCE)
    except Exception:  # noqa: BLE001
        return {}


def _caption(step) -> str:
    action = getattr(step, "action", None)
    cap = getattr(action, "caption", None) or getattr(step, "caption", None)
    return cap or "acting…"


def _finish_event(s) -> dict:
    coords = getattr(s, "failure_coords", None)
    return {
        "event": "persona_finished",
        "persona_id": s.persona_id,
        "outcome": s.outcome.value,
        "steps_survived": s.steps_survived,
        "failure_coords": list(coords) if coords else None,
    }


def _synth_events(report: RunReport) -> list[dict]:
    """Reconstruct the live-progress event stream from a recorded report so the
    replay is identical to the run that produced it. Steps interleave round-robin
    and each agent 'finishes' right after its own last step, so the cadence reflects
    the real per-persona step counts — nothing fabricated. failure_coords is looked
    up from PersonaResult (it does not live on the survival summary)."""
    results_by_id = {r.persona_id: r for r in report.results}
    coords_by_id = {r.persona_id: r.failure_coords for r in report.results}
    order = list(report.survival)

    events: list[dict] = [
        {"event": "run_started", "personas": [s.persona_id for s in order]}
    ]
    for s in order:
        events.append({"event": "persona_started", "persona_id": s.persona_id})

    step_streams = {
        s.persona_id: list(getattr(results_by_id.get(s.persona_id), "steps", []) or [])
        for s in order
    }
    finished: set[str] = set()
    max_len = max((len(v) for v in step_streams.values()), default=0)
    for i in range(max_len):
        for s in order:
            steps = step_streams[s.persona_id]
            if i < len(steps):
                st = steps[i]
                events.append({
                    "event": "step",
                    "persona_id": s.persona_id,
                    "step": getattr(st, "step", i),
                    "caption": _caption(st),
                })
                if i == len(steps) - 1:
                    ev = _finish_event(s)
                    ev["failure_coords"] = list(coords_by_id[s.persona_id]) if coords_by_id.get(s.persona_id) else None
                    events.append(ev)
                    finished.add(s.persona_id)
    for s in order:
        if s.persona_id not in finished:
            ev = _finish_event(s)
            ev["failure_coords"] = list(coords_by_id[s.persona_id]) if coords_by_id.get(s.persona_id) else None
            events.append(ev)

    events.append({"event": "run_finished", "completion_rate": report.completion_rate})
    return events


def _play_run(report: RunReport, *, animate: bool, delay: float, quiet: bool) -> None:
    if not quiet:
        on_event = render.make_progress_printer()
        for ev in _synth_events(report):
            on_event(ev)
            if animate:
                time.sleep(delay if ev.get("event") == "persona_finished" else delay * 0.45)
    render.print_summary(report, header=not quiet)


def play(*, delay: float = 0.32, quiet: bool = False) -> bool:
    """Replay the recorded demo to the terminal. Returns False if no working
    cassette is available (caller then falls back to key guidance)."""
    working = load_cassette()
    if working is None:
        return False
    broken = load_broken_cassette()

    prov = _provenance()
    w_backend = prov.get("working_backend") or prov.get("backend", "recorded")
    b_backend = prov.get("broken_backend") or prov.get("backend", "recorded")
    when = prov.get("captured_at", "")
    when_suffix = f", {when}" if when else ""
    animate = sys.stdout.isatty() and delay > 0

    print(render._bold("Simulation Labs — behavioral gate demo"))
    print(
        render._amber("▷ No key set — replaying real recorded runs.")
        + render._dim("  (set GEMINI_API_KEY to run it live)")
    )
    print(render._dim(
        f"→ genuine recorded runs of the bundled signup flow{when_suffix} — "
        "no model is called; every number below is from those runs."
    ))
    print()

    # RUN 1 — the working form. The swarm (degraded segments included) completes it.
    print(render._bold("① A working signup flow — five behavioral segments attempt it:"))
    _play_run(working, animate=animate, delay=delay, quiet=quiet)
    w_pct = f"{working.completion_rate * 100:.0f}%"
    print(render._green(f"  gate PASS ✓  — completion {w_pct}. This is your green baseline."))

    if broken is not None:
        # RUN 2 — the SAME swarm on a build where a regression broke the flow.
        print()
        print(render._bold("② The same flow on a regressed build (a deploy broke the submit):"))
        _play_run(broken, animate=animate, delay=delay, quiet=quiet)
        b_pct = f"{broken.completion_rate * 100:.0f}%"
        print(render._red(
            f"  gate FAIL ✗  — completion {b_pct} (was {w_pct}). "
            "The build broke the flow — the merge is blocked. (exit 1)"
        ))
        print()
        print(render._dim(
            "That's the whole contract: green when your users can finish, red — with the "
            "exact failures — when they can't."
        ))

    print()
    prov_note = (
        f"working run: {w_backend}; regressed-build run: {b_backend}{when_suffix}"
        if broken is not None else f"{w_backend}{when_suffix}"
    )
    print(
        render._amber("▷ recorded")
        + render._dim(
            f" ({prov_note}) · set GEMINI_API_KEY to run this live, "
            "or point it at your own flow:"
        )
    )
    print("  " + render._dim(
        'sim gate --url https://your-app.com/signup --task "create an account"'
    ))
    return True
