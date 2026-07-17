"""Headless swarm driver — Agent A owns this file.

Drives the existing engine directly (there is NO server in Phase 1): launch one
headless Chromium, wire a ``SwarmManager`` with voice OFF, start a run, block on
its task handle, and hand back the ``RunReport`` (or the error string). Follows the
"headless swarm driver" recipe in PHASE1_SPEC.md verbatim.

The signatures below are FROZEN (main.py imports them); only the bodies changed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from ghostpanel_contracts import RunReport

from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub


@dataclass
class RunOutcome:
    """Result of driving one flow to completion."""

    report: Optional[RunReport]   # None when the swarm crashed (see `error`)
    error: Optional[str]
    run_id: str
    out_dir: Path


def _build_holo(fixture: bool, rpm: Optional[int]) -> Any:
    """Pick the inference client: a deterministic Fake for fixtures/tests, else the
    configured model backend (``MODEL_BACKEND``: holo | selfhost | echo) built from
    the server settings. Routing through ``build_model`` means CLI/CI runs (the
    ``simulationlabs/gate`` conversion gate) honour the SAME vendor-agnostic seam as
    the server and worker — so a paid Holo key or a self-hosted vLLM endpoint both
    work here with no code change. ``rpm`` overrides ``Settings.hai_rpm`` when given."""
    if fixture:
        return FakeHoloClient(scripted_actions=None)
    # Late import so `--fixture` runs never touch env/settings machinery.
    import dataclasses

    from ghostpanel.engine.models.registry import build_model, default_backend
    from ghostpanel.server.config import get_settings

    settings = get_settings()
    if rpm is not None:
        settings = dataclasses.replace(settings, hai_rpm=float(rpm))
    return build_model(default_backend(), settings)


async def _consume_events(
    queue: "asyncio.Queue", on_event: Callable[[dict], None]
) -> None:
    """Forward every event the hub publishes to ``on_event`` until cancelled.

    ``on_event`` is synchronous with no await points, so cancellation can only
    land on ``queue.get()`` — never mid-callback — so no event is delivered half
    way. Callback errors are swallowed: progress display must never break a run.
    """
    while True:
        event = await queue.get()
        try:
            on_event(event)
        except Exception:  # noqa: BLE001 - a progress hiccup must not kill the run
            pass


def run_flow(
    *,
    url: str,
    task: str,
    persona_ids: Optional[list[str]] = None,
    out_dir: Path,
    fixture: bool = False,
    rpm: Optional[int] = None,
    on_event: Optional[Callable[[dict], None]] = None,
) -> RunOutcome:
    """Drive one flow's swarm headlessly and return the RunReport.

    Sync wrapper (uses asyncio.run) around the SwarmManager recipe in the spec.
    Writes `<out_dir>/<run_id>/report.html` (via the engine) and returns the report;
    the caller is responsible for `<out_dir>/report.json`. `on_event` receives live
    RunEvent dicts (from hub.subscribe) for progress display, if provided.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    holo = _build_holo(fixture, rpm)

    async def _run() -> RunOutcome:
        from playwright.async_api import async_playwright

        pw = None
        browser = None
        consumer: Optional[asyncio.Task] = None
        queue = None
        run_id = ""
        hub = WebSocketHub()
        registry = RunRegistry()
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
            swarm = SwarmManager(
                browser=browser,
                holo_client=holo,
                hub=hub,
                registry=registry,
                artifact_dir=out_dir,
                # voice OFF: no voice_engine_factory / voice_assigner.
                anthropic_key=None,
            )
            run_id = await swarm.start_run(url, task, persona_ids)

            if on_event is not None:
                # subscribe() pre-loads the backlog, so events emitted between
                # start_run() and here are replayed — none are lost.
                queue = hub.subscribe(run_id)
                consumer = asyncio.create_task(_consume_events(queue, on_event))

            record = registry.get(run_id)
            try:
                await record.task_handle    # blocks until the run finishes
            except Exception:  # noqa: BLE001 - error captured on the record below
                pass

            record = registry.get(run_id)
            return RunOutcome(
                report=record.report,
                error=(record.error or None),
                run_id=run_id,
                out_dir=out_dir,
            )
        except Exception as exc:  # noqa: BLE001 - launch/infra failure => RUN_ERROR
            return RunOutcome(
                report=None,
                error=f"{type(exc).__name__}: {exc}"[:300],
                run_id=run_id or "n/a",
                out_dir=out_dir,
            )
        finally:
            if consumer is not None:
                consumer.cancel()
                try:
                    await consumer
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
                # Drain any events that arrived after the last get() but before cancel.
                if queue is not None and on_event is not None:
                    while True:
                        try:
                            event = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        try:
                            on_event(event)
                        except Exception:  # noqa: BLE001
                            pass
                if queue is not None:
                    hub.unsubscribe(run_id, queue)
            if browser is not None:
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001
                    pass
            if pw is not None:
                try:
                    await pw.stop()
                except Exception:  # noqa: BLE001
                    pass

    return asyncio.run(_run())
