"""Swarm worker: claims jobs and runs them. Agent P2-D. Entrypoint FROZEN.

Long-running loop: one shared headless browser + one shared rate-limited
LiveHoloClient (respecting Settings.hai_rpm — the hard cap), claim a job, create
the RunRow, drive the SwarmManager to a RunReport (reuse the Phase-1 recipe /
ghostpanel.cli.driver patterns but persist via Store + publish artifacts via
ArtifactStorage), then mark the job done/failed. Concurrency = Settings.worker_concurrency.

Test seam: the run-driving logic lives in the standalone awaitable ``run_job``,
which takes the shared ``browser`` and ``holo_client`` as explicit arguments. Tests
inject a ``FakeHoloClient`` + a real headless chromium and call ``run_job`` directly
(no queue loop, no live Holo credentials required).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from pathlib import Path
from typing import Any, Optional

from ghostpanel.server.config import Settings, get_settings
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub
from ghostpanel.store import db
from ghostpanel.store.models import JobRow, RunState
from ghostpanel.store.repo import Store
from ghostpanel.storage.base import ArtifactStorage
from ghostpanel.storage.factory import build_storage

from .queue import JobQueue

logger = logging.getLogger("ghostpanel.worker")


def build_holo_client(settings: Settings) -> Optional[Any]:
    """Build the ONE shared, rate-limited Holo client (Settings.hai_rpm is the hard
    cap for the whole swarm). Returns None when no API key is configured — the worker
    still runs, but those jobs error at drive time. Never crashes on import/build."""
    if not settings.hai_api_key.strip():
        logger.warning(
            "HAI_API_KEY is empty — worker will run but every claimed job will ERROR "
            "(no Holo client). Set HAI_API_KEY to actually drive swarms."
        )
        return None
    try:
        from ghostpanel.engine.holo_client import LiveHoloClient

        return LiveHoloClient(
            api_key=settings.hai_api_key,
            base_url=settings.holo_base_url,
            model=settings.hai_model,
            rpm=settings.hai_rpm,
        )
    except Exception as exc:  # noqa: BLE001 - never let client build crash the worker
        logger.warning("Failed to build LiveHoloClient (%s); jobs will ERROR.", exc)
        return None


async def run_job(
    job: JobRow,
    *,
    store: Store,
    queue: JobQueue,
    storage: ArtifactStorage,
    settings: Settings,
    browser: Any,
    holo_client: Any,
) -> str:
    """Drive one claimed job to a persisted RunReport. Unit-testable in isolation.

    Mirrors the headless-swarm recipe in ``cli/driver.run_flow`` / ``server.swarm``
    but (a) reuses the caller's shared ``browser`` + ``holo_client`` instead of
    launching its own, and (b) persists via ``Store`` + publishes artifacts via
    ``ArtifactStorage`` instead of returning a ``RunOutcome``.

    The SwarmManager mints its own ``run_id`` (uuid hex 12) and writes artifacts to
    ``artifact_dir/<run_id>/``; we adopt that id as the canonical run_id so the
    RunRow, the report_json (``report.run_id``), and the artifact keys all agree and
    the ``/artifacts/<run_id>/report.html`` links the report emits stay valid.

    Returns the run_id. Marks the job done/failed and the run FINISHED/ERROR itself.
    """
    if holo_client is None:
        err = "no Holo client configured (HAI_API_KEY empty)"
        await queue.mark_failed(job.id, err)
        return ""

    spec = dict(job.spec or {})
    url = spec.get("url", "")
    task = spec.get("task", "")
    persona_ids = spec.get("persona_ids") or []
    flow_name = spec.get("flow_name", "")

    # Per-run artifacts land under settings.artifact_dir/<run_id>/ (the SwarmManager
    # nests by its run_id), which is exactly the layout the report URLs assume.
    artifact_dir = Path(settings.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    hub = WebSocketHub()
    registry = RunRegistry()
    swarm = SwarmManager(
        browser=browser,
        holo_client=holo_client,
        hub=hub,
        registry=registry,
        artifact_dir=artifact_dir,
        anthropic_key=None,  # voice OFF (no voice_engine_factory / voice_assigner)
    )

    run_id = await swarm.start_run(url, task, persona_ids)
    # Record the run as RUNNING and wire it to the job right away.
    await store.create_run(
        run_id=run_id,
        project_id=job.project_id,
        target_url=url,
        task=task,
        persona_ids=list(persona_ids),
        flow_name=flow_name,
        state=RunState.RUNNING,
    )
    await queue.attach_run(job.id, run_id)

    record = registry.get(run_id)
    try:
        if record is not None and record.task_handle is not None:
            await record.task_handle  # blocks until the swarm finishes
    except Exception:  # noqa: BLE001 - error is captured on the record below
        pass

    record = registry.get(run_id)
    report = record.report if record is not None else None
    error = (record.error if record is not None else "") or ""

    if report is not None:
        await store.set_run_report(run_id, report)
        try:
            await storage.put_dir(run_id, artifact_dir / run_id)
        except Exception as exc:  # noqa: BLE001 - a publish hiccup must not fail the job
            logger.warning("Artifact publish failed for run %s: %s", run_id, exc)
        await queue.mark_done(job.id)
    else:
        error = error or "swarm produced no report"
        await store.set_run_state(run_id, RunState.ERROR, error=error[:300])
        await queue.mark_failed(job.id, error)

    return run_id


async def _worker_loop(
    worker_id: str,
    *,
    store: Store,
    queue: JobQueue,
    storage: ArtifactStorage,
    settings: Settings,
    browser: Any,
    holo_client: Any,
    stop_event: asyncio.Event,
) -> None:
    """Claim-and-run loop for a single concurrency slot."""
    while not stop_event.is_set():
        try:
            job = await queue.claim(worker_id)
        except Exception as exc:  # noqa: BLE001 - a claim hiccup must not kill the loop
            logger.warning("[%s] claim error: %s", worker_id, exc)
            job = None
        if job is None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            continue
        logger.info("[%s] claimed job %s (attempt %s)", worker_id, job.id, job.attempts)
        try:
            run_id = await run_job(
                job,
                store=store,
                queue=queue,
                storage=storage,
                settings=settings,
                browser=browser,
                holo_client=holo_client,
            )
            logger.info("[%s] finished job %s -> run %s", worker_id, job.id, run_id or "n/a")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - safety net: run_job usually self-marks
            logger.exception("[%s] job %s crashed", worker_id, job.id)
            try:
                await queue.mark_failed(job.id, f"{type(exc).__name__}: {exc}"[:300])
            except Exception:  # noqa: BLE001
                pass


async def _amain() -> int:
    settings = get_settings()
    await db.init_db()

    store = Store()
    queue = JobQueue()
    storage = build_storage(settings)
    holo_client = build_holo_client(settings)

    concurrency = max(1, settings.worker_concurrency)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - non-unix
            pass

    pw = None
    browser = None
    worker_prefix = f"{socket.gethostname()}:{os.getpid()}"
    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        logger.info(
            "Worker up: %s slot(s), backend=%s, holo=%s",
            concurrency,
            settings.storage_backend,
            "live" if holo_client is not None else "DISABLED",
        )

        tasks = [
            asyncio.create_task(
                _worker_loop(
                    f"{worker_prefix}#{i}",
                    store=store,
                    queue=queue,
                    storage=storage,
                    settings=settings,
                    browser=browser,
                    holo_client=holo_client,
                    stop_event=stop_event,
                )
            )
            for i in range(concurrency)
        ]

        await stop_event.wait()
        logger.info("Shutdown signal received; draining %s worker slot(s)...", concurrency)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
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
    logger.info("Worker stopped cleanly.")
    return 0


def main() -> int:
    """`ghostpanel-worker` console entrypoint. Build engine/store/queue/storage from
    Settings, init_db, then run the claim loop until SIGINT. Returns an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:  # pragma: no cover - belt-and-suspenders for SIGINT
        return 0


__all__ = ["main", "run_job", "build_holo_client"]
