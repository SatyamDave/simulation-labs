"""Keyless-demo replay — Agent A owns this file.

`sim try` with no model key REPLAYS a real, previously-captured run of the bundled
demo flow (see recorded_demo.py) instead of dead-ending on a missing key. This is
the honest asciinema pattern: every number, caption and outcome comes from a
genuine recorded run, replayed deterministically through the SAME renderer a live
run uses — so no model is called, no key/browser/network is needed, and a stranger
sees the real result in seconds. A live run (a key set, or `sim try --live`)
always overrides this.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

from ghostpanel_contracts import RunReport

from . import render


def load_cassette() -> Optional[RunReport]:
    """Parse the shipped recorded run into a RunReport, or None if unavailable."""
    try:
        from . import recorded_demo

        return RunReport.model_validate(json.loads(recorded_demo.CASSETTE_JSON))
    except Exception:  # noqa: BLE001 — a missing/corrupt cassette must not crash `sim try`
        return None


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


def _synth_events(report: RunReport) -> list[dict]:
    """Reconstruct the live-progress event stream from the recorded report so the
    replay is identical to the run that produced it. Steps are interleaved
    round-robin and each agent 'finishes' right after its own last step — so the
    cadence reflects the real per-persona step counts, not a fabricated order."""
    results_by_id = {r.persona_id: r for r in report.results}
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
                    events.append(_finish_event(s))
                    finished.add(s.persona_id)
    for s in order:
        if s.persona_id not in finished:
            events.append(_finish_event(s))

    events.append({"event": "run_finished", "completion_rate": report.completion_rate})
    return events


def _finish_event(s) -> dict:
    coords = getattr(s, "failure_coords", None)
    return {
        "event": "persona_finished",
        "persona_id": s.persona_id,
        "outcome": s.outcome.value,
        "steps_survived": s.steps_survived,
        "failure_coords": list(coords) if coords else None,
    }


def play(*, delay: float = 0.32) -> bool:
    """Replay the recorded demo run to the terminal. Returns False if no cassette
    is available (caller should then fall back to key guidance)."""
    report = load_cassette()
    if report is None:
        return False

    prov = _provenance()
    backend = prov.get("backend", "recorded")
    when = prov.get("captured_at", "")
    when_suffix = f", {when}" if when else ""

    print(render._bold("Simulation Labs — behavioral gate demo"))
    print(
        render._amber("▷ No key set — replaying a recorded run.")
        + render._dim("  (set GEMINI_API_KEY to run it live)")
    )
    print(render._dim(
        f"→ a real {backend} run of the bundled signup flow{when_suffix} — "
        "no model is called; every number below is from that run."
    ))
    print()

    on_event = render.make_progress_printer()
    animate = sys.stdout.isatty() and delay > 0
    for ev in _synth_events(report):
        on_event(ev)
        if animate:
            time.sleep(delay if ev.get("event") == "persona_finished" else delay * 0.45)

    render.print_summary(report)

    print(
        render._amber("▷ recorded run")
        + render._dim(
            f" ({backend}{when_suffix}) · set GEMINI_API_KEY to run this live "
            "against the demo — or point it at your own flow:"
        )
    )
    print("  " + render._dim(
        'sim gate --url https://your-app.com/signup --task "create an account"'
    ))
    return True
