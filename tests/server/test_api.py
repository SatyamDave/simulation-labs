"""FastAPI surface tests — TestClient + stub swarm, no browser, no keys."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ghostpanel_contracts import PersonaOutcome, RunReport

from ghostpanel.app import create_app
from ghostpanel.server.config import Settings
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub
from server_stubs import StubAgent, StubHolo, StubReportBuilder, StubRunner, make_personas

TARGET = "http://localhost:9999/hostile_form.html"
TASK = "Sign up for the newsletter"


@pytest.fixture()
def client(tmp_path):
    """App wired with stubs but the REAL hub + WebSocketEventSink (default
    sink_factory), so the WS endpoint carries genuine RunEvent JSON."""
    settings = Settings(artifact_dir=tmp_path / "artifacts")
    swarm = SwarmManager(
        settings,
        WebSocketHub(),
        RunRegistry(),
        persona_loader=lambda ids: make_personas(),
        holo_factory=lambda s: StubHolo(),
        agent_factory=StubAgent,
        runner_factory=lambda browser, artifact_dir: StubRunner(
            browser, artifact_dir, {"grandma-72": PersonaOutcome.STUCK}
        ),
        report_builder_factory=StubReportBuilder,
        voice_factory=lambda s: None,
    )
    app = create_app(settings, swarm=swarm, launch_browser=False)
    with TestClient(app) as test_client:
        yield test_client


def _wait_for_report(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/runs/{run_id}/report")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.02)
    raise AssertionError(f"report for {run_id} never appeared")


def test_post_runs_returns_run_id_and_valid_report(client):
    response = client.post("/runs", json={"target_url": TARGET, "task": TASK})
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert isinstance(run_id, str) and run_id

    report = RunReport.model_validate(_wait_for_report(client, run_id))
    assert report.run_id == run_id
    assert report.target_url == TARGET and report.task == TASK
    assert len(report.results) == 2
    assert 0.0 <= report.completion_rate <= 1.0

    runs = client.get("/runs").json()
    assert [r["run_id"] for r in runs] == [run_id]
    assert runs[0]["status"] == "finished"
    assert runs[0]["completion_rate"] == report.completion_rate


def test_report_404_for_unknown_run(client):
    assert client.get("/runs/nope/report").status_code == 404


def test_websocket_streams_run_events(client):
    run_id = client.post(
        "/runs", json={"target_url": TARGET, "task": TASK, "persona_ids": None}
    ).json()["run_id"]

    # Connect while (possibly) mid-run: backlog replays first, live events follow.
    events = []
    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        while True:
            payload = ws.receive_json()
            events.append(payload)
            if payload["event"] == "run_finished":
                break

    assert events[0]["event"] == "run_started"
    assert events[0]["run_id"] == run_id
    kinds = [e["event"] for e in events]
    assert kinds.count("persona_started") == 2
    assert kinds.count("persona_finished") == 2
    assert "step" in kinds
    assert events[-1]["event"] == "run_finished"
    assert events[-1]["report_url"] == f"/runs/{run_id}/report"


def test_late_websocket_subscriber_gets_full_backlog(client):
    run_id = client.post("/runs", json={"target_url": TARGET, "task": TASK}).json()["run_id"]
    _wait_for_report(client, run_id)  # run fully finished before we connect

    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        first = ws.receive_json()
        assert first["event"] == "run_started"
        while (payload := ws.receive_json())["event"] != "run_finished":
            pass
        assert payload["completion_rate"] == 0.5
