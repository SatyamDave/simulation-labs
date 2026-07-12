"""NemoClaw policy wiring + the Ghostpanel Index (``GET /leaderboard``).

Hermetic: no browser (``launch_browser=False``), no Holo network
(``FakeHoloClient``), no voice, no docs fetch (file-mode /policy only).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ghostpanel.app import create_app
from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.server.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESET_PATH = REPO_ROOT / "policies" / "ghostpanel-browse-only.yaml"


def _make_client(tmp_path, **settings_overrides) -> TestClient:
    settings = Settings(artifact_dir=tmp_path, **settings_overrides)
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),  # no Holo network
        enable_voice=False,            # no Gradium, no Anthropic
        launch_browser=False,          # endpoint tests need no browser
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    with _make_client(tmp_path) as c:
        yield c


@pytest.fixture
def enforced_client(tmp_path):
    with _make_client(tmp_path, nemoclaw_policy_file=PRESET_PATH) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /policy — summary + enforced
# ---------------------------------------------------------------------------
def test_policy_summary_and_enforced_with_bundled_preset(enforced_client, monkeypatch):
    monkeypatch.delenv("NEMOCLAW_POLICY_FILE", raising=False)
    body = enforced_client.get("/policy").json()

    assert body["source"] == "file"
    assert body["policy"]["preset"]["name"] == "ghostpanel-browse-only"
    assert body["summary"] == {
        "preset": "ghostpanel-browse-only",
        "allowed_methods": ["GET"],
        "denied_by_default": True,
        "hosts": ["*"],
    }
    # The swarm really runs with the mirror enforcement…
    assert body["enforced"] is True
    swarm = enforced_client.app.state.swarm
    assert swarm.request_policy is not None
    # …and its default runner factory bakes the policy into every session.
    runner = swarm.runner_factory(None, Path("."), None)
    assert isinstance(runner, PlaywrightSessionRunner)
    assert runner.policy is swarm.request_policy
    # OpenShell routing status is still reported.
    assert body["gateway_url"] == "" and body["active"] is False


def test_policy_enforced_false_when_swarm_has_no_policy(client, monkeypatch):
    # Env points at the preset (file mode works) but the swarm was built
    # without it — `enforced` reflects the swarm, not the file on disk.
    monkeypatch.setenv("NEMOCLAW_POLICY_FILE", str(PRESET_PATH))
    body = client.get("/policy").json()
    assert body["source"] == "file"
    assert body["summary"]["preset"] == "ghostpanel-browse-only"
    assert body["enforced"] is False


def test_policy_summary_null_for_non_preset_yaml(client, tmp_path, monkeypatch):
    other = tmp_path / "other.yaml"
    other.write_text("policies:\n  - name: block-writes\n", encoding="utf-8")
    monkeypatch.setenv("NEMOCLAW_POLICY_FILE", str(other))
    body = client.get("/policy").json()
    assert body["source"] == "file"
    assert body["summary"] is None  # not an OpenShell preset -> nothing to summarize


# ---------------------------------------------------------------------------
# GET /leaderboard — the Ghostpanel Index
# ---------------------------------------------------------------------------
def _write_insights(artifact_dir: Path, run_dir: str, payload: dict) -> Path:
    d = artifact_dir / run_dir
    d.mkdir(parents=True, exist_ok=True)
    path = d / "insights.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_leaderboard_lists_new_and_legacy_insights(client, tmp_path):
    # Newer run: full meta/stats (the shape the report module now writes).
    _write_insights(
        tmp_path,
        "runA",
        {
            "ghostpanel_score": 72,
            "agent_readiness": {"score": 55, "outcome": "stuck", "steps": 9, "note": ""},
            "wcag_findings": [],
            "summary": "3/5 made it",
            "meta": {
                "run_id": "runA",
                "target_url": "http://a.test/",
                "task": "sign up",
                "generated_at": "2026-07-12T10:00:00+00:00",
                "personas": 5,
            },
            # Real report shape: run-level stats nested under stats.run,
            # stats.personas is the per-persona LIST (not a count).
            "stats": {
                "run": {"personas_succeeded": 3, "personas_abandoned": 2},
                "personas": [{"persona_id": f"p{i}"} for i in range(5)],
            },
        },
    )
    # Older, legacy run: no meta/stats keys at all.
    legacy = _write_insights(
        tmp_path,
        "runB-legacy",
        {
            "ghostpanel_score": 88,
            "agent_readiness": None,
            "wcag_findings": [],
            "summary": "old format",
        },
    )
    old = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(legacy, (old, old))  # mtime is the legacy sort fallback
    # A corrupt insights.json never breaks the index.
    (tmp_path / "runC-broken").mkdir()
    (tmp_path / "runC-broken" / "insights.json").write_text("{nope", encoding="utf-8")

    board = client.get("/leaderboard").json()
    assert [row["run_id"] for row in board] == ["runA", "runB-legacy"]

    top = board[0]
    assert top == {
        "run_id": "runA",
        "target_url": "http://a.test/",
        "task": "sign up",
        "ghostpanel_score": 72,
        "agent_readiness_score": 55,
        "completion_rate": 0.6,
        "personas": 5,
        "generated_at": "2026-07-12T10:00:00+00:00",
    }
    legacy_row = board[1]
    assert legacy_row["ghostpanel_score"] == 88
    for null_field in (
        "target_url",
        "task",
        "agent_readiness_score",
        "completion_rate",
        "personas",
        "generated_at",
    ):
        assert legacy_row[null_field] is None, null_field


def test_leaderboard_caps_at_50_newest(client, tmp_path):
    for i in range(55):
        _write_insights(
            tmp_path,
            f"run{i:02d}",
            {
                "ghostpanel_score": i,
                "meta": {
                    "run_id": f"run{i:02d}",
                    "generated_at": f"2026-06-{(i % 28) + 1:02d}T00:00:{i:02d}+00:00",
                },
            },
        )
    board = client.get("/leaderboard").json()
    assert len(board) == 50
    # Newest-first by generated_at.
    stamps = [row["generated_at"] for row in board]
    assert stamps == sorted(stamps, reverse=True)


def test_leaderboard_empty_when_no_insights(client):
    assert client.get("/leaderboard").json() == []
