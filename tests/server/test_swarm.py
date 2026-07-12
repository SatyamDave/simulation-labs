"""SwarmManager integration tests.

Fully hermetic for Holo (``FakeHoloClient`` — no network) but drives a REAL
headless ``PlaywrightSessionRunner`` against ``fixtures/hostile_form.html`` served
over a localhost http.server. Voice + LLM narration are disabled (offline).
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.server.runs import RunRegistry, RunStatus
from ghostpanel.server.swarm import SwarmManager, _default_agent_factory
from ghostpanel.server.ws import WebSocketHub
from ghostpanel_contracts import PersonaOutcome, RunReport

REPO_ROOT = Path(__file__).resolve().parents[2]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence request logging
        pass


@pytest.fixture(scope="session")
def http_base():
    handler = functools.partial(_QuietHandler, directory=str(REPO_ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def target_url(http_base):
    return f"{http_base}/fixtures/hostile_form.html"


@pytest.fixture
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


def _make_swarm(browser, hub, registry, tmp_path, **overrides) -> SwarmManager:
    return SwarmManager(
        browser=browser,
        holo_client=FakeHoloClient(),  # empty script -> center clicks -> stuck fast
        hub=hub,
        registry=registry,
        artifact_dir=tmp_path,
        anthropic_key=None,          # template transcripts only, no network
        voice_engine_factory=None,   # no Gradium
        **overrides,
    )


async def test_swarm_runs_two_personas_and_caches_report(browser, tmp_path, target_url):
    hub = WebSocketHub()
    registry = RunRegistry()
    swarm = _make_swarm(browser, hub, registry, tmp_path)

    run_id = await swarm.start_run(target_url, "sign up", ["grandma-72", "power-user"])
    record = registry.get(run_id)
    assert record is not None
    await record.task_handle  # block until the swarm settles

    # A RunReport was produced and cached.
    assert record.status == RunStatus.FINISHED
    report = record.report
    assert isinstance(report, RunReport)
    assert report.run_id == run_id
    assert len(report.results) == 2
    assert 0.0 <= report.completion_rate <= 1.0

    # Report HTML was written under <artifact_dir>/<run_id>/report.html.
    assert (tmp_path / run_id / "report.html").exists()

    # RunStarted ... RunFinished (and per-persona events) reached the hub buffer.
    events = hub.buffer(run_id)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert "persona_started" in kinds
    assert "step" in kinds
    assert "persona_finished" in kinds

    # Non-success personas get an exit-interview transcript (template fallback).
    for result in report.results:
        if result.outcome != PersonaOutcome.SUCCESS:
            assert result.transcript


async def test_swarm_survives_a_persona_error(browser, tmp_path, target_url):
    hub = WebSocketHub()
    registry = RunRegistry()

    def agent_factory(persona, holo, task):
        if persona.id == "power-user":
            raise RuntimeError("boom: simulated agent construction failure")
        return _default_agent_factory(persona, holo, task)

    swarm = _make_swarm(
        browser, hub, registry, tmp_path, agent_factory=agent_factory
    )

    run_id = await swarm.start_run(target_url, "sign up", ["grandma-72", "power-user"])
    record = registry.get(run_id)
    await record.task_handle  # must NOT raise despite the failing persona

    report = record.report
    assert report is not None
    assert record.status == RunStatus.FINISHED
    outcomes = {r.persona_id: r.outcome for r in report.results}
    assert outcomes["power-user"] == PersonaOutcome.ERROR
    # The other persona ran normally (some non-error terminal outcome).
    assert outcomes["grandma-72"] != PersonaOutcome.ERROR
    # ERROR personas are excluded from the completion denominator -> still valid.
    assert 0.0 <= report.completion_rate <= 1.0
    # The run still finished and broadcast a terminal event.
    assert hub.buffer(run_id)[-1]["event"] == "run_finished"


async def test_start_run_falls_back_to_full_roster_for_unknown_ids(
    browser, tmp_path, target_url
):
    hub = WebSocketHub()
    registry = RunRegistry()
    swarm = _make_swarm(browser, hub, registry, tmp_path)

    run_id = await swarm.start_run(target_url, "sign up", ["does-not-exist"])
    record = registry.get(run_id)
    await record.task_handle
    # Unknown ids -> full roster (8 personas exist).
    assert record.report is not None
    assert len(record.report.results) == 8
