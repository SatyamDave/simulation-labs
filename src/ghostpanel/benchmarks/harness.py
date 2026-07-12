"""Benchmark harness — measure swarm quality and runner performance on known flows.

Runs the real persona/runner stack against bundled benchmark pages served from a
local HTTP server, and reports per-persona outcomes plus latency/overhead metrics.
Two modes:

* **offline** (default) — ``FakeHoloClient`` (center clicks, no network). Personas
  can't complete flows, but the run measures the runner loop itself: wall-clock
  per step (screenshot + thumbnail + execute + settle) with zero model latency.
* **live** — ``LiveHoloClient`` with the keys/RPM from ``.env``. Measures agent
  QUALITY: completion rate per case, steps-to-success, simulated duration, and
  Holo latency percentiles. The `easy` case is the control — every persona should
  pass it; failures there are engine/runner regressions, not site findings.

Success on every benchmark page is "``#ok`` is visible" (the same marker
``fixtures/hostile_form.html`` already uses).

Usage: ``python -m ghostpanel.benchmarks [--live] [--cases easy,hostile] ...``
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import statistics
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from ghostpanel_contracts import PersonaConfig, PersonaOutcome, PersonaResult

from ghostpanel.engine.holo_client import FakeHoloClient, LiveHoloClient
from ghostpanel.engine.persona_agent import HoloPersonaAgent
from ghostpanel.engine.personas import load_personas
from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.runner.testing import CollectingEventSink
from ghostpanel.server.config import get_settings

# repo root: src/ghostpanel/benchmarks/harness.py -> parents[3] (same as server.config)
_REPO_ROOT = Path(__file__).resolve().parents[3]

# (persona, holo, task) -> PersonaAgent. Same shape as server.swarm.AgentFactory.
AgentFactory = Callable[[PersonaConfig, Any, str], Any]


@dataclass(frozen=True)
class BenchCase:
    """One benchmark flow: a repo-relative page and the task to attempt on it."""

    id: str
    page: str  # path relative to the repo root, served over local HTTP
    task: str
    ok_selector: str = "#ok"


BUILTIN_CASES: tuple[BenchCase, ...] = (
    BenchCase(
        id="easy",
        page="benchmarks/pages/easy_form.html",
        task="Create an account: fill in the email and password fields and submit the form.",
    ),
    BenchCase(
        id="hostile",
        page="fixtures/hostile_form.html",
        task="Create an account: accept cookies, fill the form, and submit it.",
    ),
)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass


def _serve_repo_root() -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serve the repo root on an ephemeral port; returns (server, base_url)."""
    handler = functools.partial(_QuietHandler, directory=str(_REPO_ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _ok_predicate(selector: str):
    async def _visible(page) -> bool:  # noqa: ANN001 - live Playwright page
        return await page.locator(selector).is_visible()

    return _visible


def _default_agent_factory(persona: PersonaConfig, holo: Any, task: str) -> Any:
    return HoloPersonaAgent(persona, holo, task=task)


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def _persona_metrics(result: PersonaResult, wall_s: float) -> dict:
    latencies = [s.latency_ms for s in result.steps if s.latency_ms > 0]
    holo_s = sum(latencies) / 1000.0
    steps = len(result.steps)
    return {
        "persona_id": result.persona_id,
        "outcome": result.outcome.value,
        "steps": steps,
        "sim_s": round(result.duration_s, 1),
        "wall_s": round(wall_s, 1),
        "holo_mean_ms": int(statistics.mean(latencies)) if latencies else 0,
        "holo_p95_ms": _percentile(latencies, 95),
        # Runner overhead per step: wall time not spent waiting on the model.
        "overhead_ms_per_step": int((wall_s - holo_s) / steps * 1000) if steps else 0,
        "failure_reason": result.failure_reason,
    }


async def _run_case(
    case: BenchCase,
    base_url: str,
    personas: list[PersonaConfig],
    holo: Any,
    browser: Any,
    artifact_dir: Path,
    agent_factory: AgentFactory,
) -> dict:
    url = f"{base_url}/{case.page}"
    predicate = _ok_predicate(case.ok_selector)

    async def _one(persona: PersonaConfig) -> dict:
        runner = PlaywrightSessionRunner(browser, artifact_dir, success_predicate=predicate)
        agent = agent_factory(persona, holo, case.task)
        t0 = time.monotonic()
        result = await runner.run(
            persona, agent, url, case.task, CollectingEventSink(), f"bench-{case.id}"
        )
        return _persona_metrics(result, time.monotonic() - t0)

    rows = await asyncio.gather(*(_one(p) for p in personas))
    successes = [r for r in rows if r["outcome"] == PersonaOutcome.SUCCESS.value]
    scored = [r for r in rows if r["outcome"] != PersonaOutcome.ERROR.value]
    return {
        "case": case.id,
        "task": case.task,
        "completion_rate": round(len(successes) / len(scored), 3) if scored else 0.0,
        "mean_steps_to_success": (
            round(statistics.mean(r["steps"] for r in successes), 1) if successes else None
        ),
        "personas": list(rows),
    }


async def run_benchmark(
    case_ids: Optional[list[str]] = None,
    persona_ids: Optional[list[str]] = None,
    live: bool = False,
    artifact_dir: Optional[Path] = None,
    agent_factory: AgentFactory = _default_agent_factory,
    browser: Any = None,
) -> dict:
    """Run the selected benchmark cases and return a JSON-serializable report.

    ``browser`` may be injected (tests reuse one); otherwise Chromium is launched
    and closed here. ``live=True`` requires HAI_API_KEY in the environment/.env.
    """
    cases = [c for c in BUILTIN_CASES if case_ids is None or c.id in case_ids]
    if not cases:
        raise ValueError(f"No benchmark cases match {case_ids!r}")
    personas = load_personas(persona_ids)
    if not personas:
        raise ValueError(f"No personas match {persona_ids!r}")

    if live:
        settings = get_settings()
        if not settings.hai_api_key:
            raise RuntimeError("live benchmark needs HAI_API_KEY (see .env.example)")
        holo = LiveHoloClient(
            settings.hai_api_key, settings.holo_base_url, settings.hai_model,
            rpm=settings.hai_rpm,
        )
    else:
        holo = FakeHoloClient()

    artifact_dir = artifact_dir or (_REPO_ROOT / "artifacts" / "benchmarks")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    server, base_url = _serve_repo_root()
    own_browser = browser is None
    playwright = None
    try:
        if own_browser:
            from playwright.async_api import async_playwright

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)

        t0 = time.monotonic()
        case_reports = []
        for case in cases:  # sequential so cases don't fight over the RPM budget
            case_reports.append(
                await _run_case(case, base_url, personas, holo, browser,
                                artifact_dir, agent_factory)
            )
        return {
            "mode": "live" if live else "offline",
            "personas": [p.id for p in personas],
            "wall_s": round(time.monotonic() - t0, 1),
            "cases": case_reports,
        }
    finally:
        server.shutdown()
        server.server_close()
        if own_browser and browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()


def format_scoreboard(report: dict) -> str:
    """Render a report as a fixed-width scoreboard for the terminal."""
    lines = [
        f"Ghostpanel benchmark — mode: {report['mode']}, "
        f"total wall: {report['wall_s']}s",
    ]
    for case in report["cases"]:
        done = f"{case['completion_rate'] * 100:.0f}%"
        mean_steps = case["mean_steps_to_success"]
        lines.append("")
        lines.append(
            f"[{case['case']}] completion {done}"
            + (f", mean steps to success {mean_steps}" if mean_steps else "")
        )
        header = (
            f"  {'persona':<18} {'outcome':<12} {'steps':>5} {'sim_s':>7} "
            f"{'wall_s':>7} {'holo_mean':>9} {'holo_p95':>8} {'ovh/step':>8}"
        )
        lines.append(header)
        for r in case["personas"]:
            lines.append(
                f"  {r['persona_id']:<18} {r['outcome']:<12} {r['steps']:>5} "
                f"{r['sim_s']:>7} {r['wall_s']:>7} {r['holo_mean_ms']:>7}ms "
                f"{r['holo_p95_ms']:>6}ms {r['overhead_ms_per_step']:>6}ms"
            )
    return "\n".join(lines)
