"""Memory-layer wiring tests for the orchestrator.

Covers the seam between the ``ghostpanel.memory`` store and the server:
  * a run's ``memory_mode`` reaches ``start_run`` / the RunRecord (GET /runs),
  * recalled hints are prepended to the task the persona agent receives,
  * ``remember_run`` fires once after a run completes,
  * GET /insights returns the documented shape,
  * config degrades to NullMemoryStore when no Supermemory key is set.

Holo is faked (no network); a REAL headless browser drives the hostile form over
a localhost http.server, matching ``test_api``/``test_swarm``.
"""

from __future__ import annotations

import functools
import http.server
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from ghostpanel.app import create_app
from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.memory import (
    InsightRecord,
    MemoryStore,
    NullMemoryStore,
    create_memory_store,
)
from ghostpanel.server.config import Settings
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.swarm import SwarmManager, _default_agent_factory
from ghostpanel.server.ws import WebSocketHub

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- a recording fake store -------------------------------------------------
class FakeMemoryStore:
    """Records every seam call; returns scripted hints/insights. Satisfies the
    ``MemoryStore`` Protocol (``runtime_checkable``)."""

    def __init__(self, *, hints=None, insights=None):
        self._hints = list(hints or [])
        self._insights = list(insights or [])
        self.recall_hints_calls: list[dict] = []
        self.remember_run_calls: list[dict] = []
        self.recall_insights_calls: list[dict] = []
        self.closed = False

    async def recall_hints(self, *, target_url, task, persona, mode):
        self.recall_hints_calls.append(
            {"target_url": target_url, "task": task, "persona": persona, "mode": mode}
        )
        return list(self._hints)

    async def remember_run(self, *, run_id, target_url, task, report, personas):
        self.remember_run_calls.append(
            {"run_id": run_id, "target_url": target_url, "task": task}
        )
        return len(personas)

    async def recall_insights(self, *, query, limit=10, impairment=None):
        self.recall_insights_calls.append(
            {"query": query, "limit": limit, "impairment": impairment}
        )
        return list(self._insights)

    async def aclose(self):
        self.closed = True


def test_fake_store_satisfies_protocol():
    assert isinstance(FakeMemoryStore(), MemoryStore)


# --- localhost fixtures (mirror test_api) -----------------------------------
class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
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


def _wait_for_report(client: TestClient, run_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}/report")
        if resp.status_code == 200:
            return resp.json()
        time.sleep(0.5)
    raise AssertionError(f"report for {run_id} never became ready")


# --- API-level wiring -------------------------------------------------------
def test_post_run_accepts_memory_mode_and_records_it(tmp_path, target_url):
    fake = FakeMemoryStore(hints=[])
    settings = Settings(artifact_dir=tmp_path)
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),
        memory_store=fake,
        enable_voice=False,
    )
    with TestClient(app) as client:
        resp = client.post(
            "/runs",
            json={
                "target_url": target_url,
                "task": "sign up",
                "persona_ids": ["power-user"],
                "memory_mode": "site_hints",
            },
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        _wait_for_report(client, run_id)

        # memory_mode persisted onto the RunRecord and surfaced via GET /runs.
        summary = next(r for r in client.get("/runs").json() if r["run_id"] == run_id)
        assert summary["memory_mode"] == "site_hints"

    # recall_hints was invoked with the run's mode; remember_run fired once.
    assert fake.recall_hints_calls, "recall_hints was never awaited"
    assert all(c["mode"] == "site_hints" for c in fake.recall_hints_calls)
    assert len(fake.remember_run_calls) == 1
    assert fake.remember_run_calls[0]["run_id"] == run_id
    # store closed on shutdown.
    assert fake.closed is True


def test_insights_endpoint_shape(tmp_path):
    records = [
        InsightRecord(
            content="Users with tremor overshot the tiny submit button.",
            site="stripe-com",
            persona_id="grandma-72",
            persona_name="Grandma",
            impairment="tremor",
            outcome="stuck",
            steps_survived=7,
            score=0.42,
            metadata={"secret": "dropped"},
        )
    ]
    fake = FakeMemoryStore(insights=records)
    settings = Settings(artifact_dir=tmp_path)
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),
        memory_store=fake,
        enable_voice=False,
        launch_browser=False,
    )
    with TestClient(app) as client:
        resp = client.get("/insights", params={"q": "tremor", "limit": 5, "impairment": "tremor"})
        assert resp.status_code == 200
        body = resp.json()

    assert body["count"] == 1
    assert set(body.keys()) == {"insights", "count"}
    item = body["insights"][0]
    assert set(item.keys()) == {
        "content", "site", "persona_id", "persona_name",
        "impairment", "outcome", "steps_survived", "score",
    }
    assert "metadata" not in item  # metadata is dropped from the response
    assert item["steps_survived"] == 7
    assert item["score"] == 0.42
    # query params reached the store.
    assert fake.recall_insights_calls == [
        {"query": "tremor", "limit": 5, "impairment": "tremor"}
    ]


def test_memory_modes_endpoint(tmp_path):
    settings = Settings(artifact_dir=tmp_path, supermemory_default_mode="site_hints")
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),
        memory_store=NullMemoryStore(),
        enable_voice=False,
        launch_browser=False,
    )
    with TestClient(app) as client:
        body = client.get("/memory/modes").json()
    assert body["modes"] == ["off", "site_hints", "returning_user"]
    assert body["default"] == "site_hints"


# --- swarm-level recall injection into the agent task -----------------------
async def test_recall_hints_prepended_to_agent_task(browser, tmp_path, target_url):
    hub = WebSocketHub()
    registry = RunRegistry()
    fake = FakeMemoryStore(hints=["Click the big green Continue button first."])

    captured_tasks: list[str] = []

    def agent_factory(persona, holo, task):
        captured_tasks.append(task)
        return _default_agent_factory(persona, holo, task)

    swarm = SwarmManager(
        browser=browser,
        holo_client=FakeHoloClient(),
        hub=hub,
        registry=registry,
        artifact_dir=tmp_path,
        anthropic_key=None,
        voice_engine_factory=None,
        agent_factory=agent_factory,
        memory_store=fake,
        default_memory_mode="site_hints",
    )

    run_id = await swarm.start_run(target_url, "sign up", ["power-user"])
    await registry.get(run_id).task_handle

    # The default mode was applied (no per-run override given).
    assert fake.recall_hints_calls[0]["mode"] == "site_hints"
    # The hint was folded into the task the agent received.
    assert captured_tasks, "agent_factory was never called"
    assert "sign up" in captured_tasks[0]
    assert "Click the big green Continue button first." in captured_tasks[0]
    assert "What helped previous visitors" in captured_tasks[0]
    # remember_run fired once after the run completed.
    assert len(fake.remember_run_calls) == 1


async def test_per_run_mode_overrides_default(browser, tmp_path, target_url):
    hub = WebSocketHub()
    registry = RunRegistry()
    fake = FakeMemoryStore(hints=[])
    swarm = SwarmManager(
        browser=browser,
        holo_client=FakeHoloClient(),
        hub=hub,
        registry=registry,
        artifact_dir=tmp_path,
        memory_store=fake,
        default_memory_mode="off",
    )
    run_id = await swarm.start_run(
        target_url, "sign up", ["power-user"], memory_mode="returning_user"
    )
    await registry.get(run_id).task_handle
    assert registry.get(run_id).memory_mode == "returning_user"
    assert all(c["mode"] == "returning_user" for c in fake.recall_hints_calls)


# --- config degradation -----------------------------------------------------
def test_no_api_key_yields_null_store():
    # Factory: empty key -> NullMemoryStore, no supermemory SDK required.
    store = create_memory_store(api_key="", default_mode="off")
    assert isinstance(store, NullMemoryStore)


def test_settings_memory_defaults():
    s = Settings()
    assert s.has_memory is False
    assert s.supermemory_default_mode == "off"


def test_app_builds_without_memory_config(tmp_path, target_url):
    """No memory_store injected + no key -> NullMemoryStore, runs still work and
    memory_mode defaults to 'off'."""
    settings = Settings(artifact_dir=tmp_path)  # no supermemory_api_key
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),
        enable_voice=False,
    )
    with TestClient(app) as client:
        assert isinstance(app.state.memory_store, NullMemoryStore)
        resp = client.post(
            "/runs",
            json={"target_url": target_url, "task": "sign up", "persona_ids": ["power-user"]},
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        _wait_for_report(client, run_id)
        summary = next(r for r in client.get("/runs").json() if r["run_id"] == run_id)
        assert summary["memory_mode"] == "off"
