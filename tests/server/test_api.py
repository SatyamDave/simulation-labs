"""FastAPI surface tests via TestClient.

Uses a real headless browser (started by the app's startup event) + a
``FakeHoloClient`` (no Holo network) with voice/LLM narration disabled. The
hostile form is served over a localhost http.server.
"""

from __future__ import annotations

import functools
import http.server
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ghostpanel.app import create_app
from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.server.ws import WebSocketEventSink, WebSocketHub
from ghostpanel_contracts import EventSink

REPO_ROOT = Path(__file__).resolve().parents[2]


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
def client(tmp_path):
    from ghostpanel.server.config import Settings

    settings = Settings(artifact_dir=tmp_path)
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),  # no Holo network
        enable_voice=False,            # no Gradium, no Anthropic
    )
    with TestClient(app) as c:  # triggers startup (launches browser) + shutdown
        yield c


def _wait_for_report(client: TestClient, run_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}/report")
        if resp.status_code == 200:
            return resp.json()
        time.sleep(0.5)
    raise AssertionError(f"report for {run_id} never became ready")


def test_event_sink_satisfies_protocol():
    assert isinstance(WebSocketEventSink("r", WebSocketHub()), EventSink)


def test_post_run_then_report_and_list(client, target_url):
    resp = client.post(
        "/runs",
        json={
            "target_url": target_url,
            "task": "sign up for an account",
            "persona_ids": ["grandma-72", "power-user"],
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    assert run_id

    report = _wait_for_report(client, run_id)
    # Valid RunReport JSON.
    assert report["run_id"] == run_id
    assert report["target_url"] == target_url
    assert len(report["results"]) == 2
    assert 0.0 <= report["completion_rate"] <= 1.0
    assert "survival" in report and "heatmap_points" in report

    # It shows up in the run list.
    listing = client.get("/runs").json()
    assert any(r["run_id"] == run_id for r in listing)


def test_websocket_replays_events(client, target_url):
    resp = client.post(
        "/runs",
        json={"target_url": target_url, "task": "sign up", "persona_ids": ["power-user"]},
    )
    run_id = resp.json()["run_id"]
    _wait_for_report(client, run_id)  # let the run finish; buffer holds the backlog

    kinds: list[str] = []
    with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
        while True:
            event = ws.receive_json()
            kinds.append(event["event"])
            if event["event"] == "run_finished":
                break

    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert "persona_started" in kinds
    assert "step" in kinds


def test_report_404_for_unknown_run(client):
    assert client.get("/runs/nope/report").status_code == 404
