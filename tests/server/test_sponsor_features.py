"""Sponsor-stretch feature tests: per-persona voice assignment, insights.json,
``POST /runs/{id}/ask`` (Gradium live Q&A) and ``GET /policy`` (NemoClaw relay).

Hermetic: no real browser (``launch_browser=False`` + a stub runner factory),
no Holo network (``FakeHoloClient``), no Gradium (fake voice engine/assigner),
and no NVIDIA docs fetch (file mode / an unroutable docs URL).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ghostpanel.app import create_app
from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.server.config import Settings
from ghostpanel.server.runs import RunRegistry, RunStatus
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub
from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    RunReport,
    StepRecord,
)

RUN_ID = "run-fixture-01"
PERSONA_ID = "grandma-72"


# ---------------------------------------------------------------------------
# fixtures + fakes
# ---------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    settings = Settings(
        artifact_dir=tmp_path, nemoclaw_gateway_url="http://localhost:9999/gw"
    )
    app = create_app(
        settings=settings,
        holo_client=FakeHoloClient(),  # no Holo network
        enable_voice=False,            # no Gradium, no Anthropic
        launch_browser=False,          # endpoint tests need no browser
    )
    with TestClient(app) as c:
        yield c


class _FakeVoiceEngine:
    """Stands in for GradiumVoiceEngine: writes a real file, records calls."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.calls: list[tuple[str, str | None]] = []

    async def mutter(self, text: str, voice_id: str | None) -> str:
        self.calls.append((text, voice_id))
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / "mutter-answer.wav"
        path.write_bytes(b"RIFF-fake")
        return str(path)


def _seed_finished_run(app) -> None:
    """Put a finished run (report + persona configs) straight into the registry."""
    registry = app.state.runs
    record = registry.create(RUN_ID, "http://target.test/", "sign up", [PERSONA_ID])
    steps = [
        StepRecord(
            persona_id=PERSONA_ID,
            step=i,
            action=Action(type=ActionType.CLICK, x=10, y=20, caption=cap),
        )
        for i, cap in enumerate(["Clicking Sign up", "Typing my email"])
    ]
    result = PersonaResult(
        persona_id=PERSONA_ID,
        outcome=PersonaOutcome.STUCK,
        steps=steps,
        failure_reason="the submit button never responded",
        transcript="I kept clicking and nothing happened.",
    )
    report = RunReport(
        run_id=RUN_ID, target_url="http://target.test/", task="sign up",
        results=[result],
    )
    registry.set_report(RUN_ID, report)
    record.personas = [
        PersonaConfig(id=PERSONA_ID, name="Margaret, 72", voice_id="preset-voice-1")
    ]


class _StubRunner:
    """Skips the browser entirely: every persona 'succeeds' instantly."""

    async def run(self, persona, agent, target_url, task, sink, run_id):  # noqa: ANN001
        return PersonaResult(persona_id=persona.id, outcome=PersonaOutcome.SUCCESS)


def _make_browserless_swarm(tmp_path, **overrides) -> tuple[SwarmManager, RunRegistry]:
    registry = RunRegistry()
    swarm = SwarmManager(
        browser=None,
        holo_client=FakeHoloClient(),
        hub=WebSocketHub(),
        registry=registry,
        artifact_dir=tmp_path,
        anthropic_key=None,
        voice_engine_factory=None,
        runner_factory=lambda browser, artifact_dir, predicate: _StubRunner(),
        **overrides,
    )
    return swarm, registry


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/ask
# ---------------------------------------------------------------------------
def test_ask_returns_grounded_text_and_audio(client, tmp_path):
    _seed_finished_run(client.app)
    engines: list[_FakeVoiceEngine] = []

    def factory(run_dir: Path) -> _FakeVoiceEngine:
        engine = _FakeVoiceEngine(run_dir)
        engines.append(engine)
        return engine

    client.app.state.swarm.voice_engine_factory = factory

    resp = client.post(
        f"/runs/{RUN_ID}/ask",
        json={"persona_id": PERSONA_ID, "question": "Why did you give up?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Grounded in transcript + captions + failure_reason — nothing invented.
    assert "I kept clicking and nothing happened." in body["text"]
    assert "clicking sign up" in body["text"]
    assert "typing my email" in body["text"]
    assert "the submit button never responded" in body["text"]
    # Audio synthesized with the persona's assigned voice, served via /artifacts.
    assert body["audio_url"] == f"/artifacts/{RUN_ID}/mutter-answer.wav"
    assert engines and engines[0].calls[0][1] == "preset-voice-1"
    assert (tmp_path / RUN_ID / "mutter-answer.wav").exists()


def test_ask_without_voice_engine_still_answers_with_null_audio(client):
    _seed_finished_run(client.app)
    assert client.app.state.swarm.voice_engine_factory is None

    resp = client.post(
        f"/runs/{RUN_ID}/ask",
        json={"persona_id": PERSONA_ID, "question": "What happened?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_url"] is None
    assert "the submit button never responded" in body["text"]


def test_ask_voice_failure_degrades_to_text(client):
    _seed_finished_run(client.app)

    class _BoomEngine:
        async def mutter(self, text, voice_id):  # noqa: ANN001
            raise RuntimeError("gradium down")

    client.app.state.swarm.voice_engine_factory = lambda run_dir: _BoomEngine()
    resp = client.post(
        f"/runs/{RUN_ID}/ask", json={"persona_id": PERSONA_ID, "question": "?"}
    )
    assert resp.status_code == 200
    assert resp.json()["audio_url"] is None


def test_ask_404_for_unknown_run_and_persona(client):
    _seed_finished_run(client.app)
    assert (
        client.post("/runs/nope/ask", json={"persona_id": PERSONA_ID, "question": "?"})
        .status_code
        == 404
    )
    assert (
        client.post(
            f"/runs/{RUN_ID}/ask", json={"persona_id": "nobody", "question": "?"}
        ).status_code
        == 404
    )


def test_ask_409_while_run_in_flight(client):
    registry = client.app.state.runs
    registry.create("inflight", "http://t/", "sign up", [PERSONA_ID])
    assert registry.get("inflight").status == RunStatus.RUNNING
    resp = client.post(
        "/runs/inflight/ask", json={"persona_id": PERSONA_ID, "question": "?"}
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /policy
# ---------------------------------------------------------------------------
def test_policy_serves_local_yaml_file(client, tmp_path, monkeypatch):
    policy_path = tmp_path / "nemoclaw-policy.yaml"
    policy_path.write_text(
        "policies:\n  - name: block-writes\n    action: deny\n", encoding="utf-8"
    )
    monkeypatch.setenv("NEMOCLAW_POLICY_FILE", str(policy_path))

    body = client.get("/policy").json()
    assert body["source"] == "file"
    assert body["policy"] == {"policies": [{"name": "block-writes", "action": "deny"}]}
    # Gateway status comes from settings so the UI can show routing state.
    assert body["gateway_url"] == "http://localhost:9999/gw"
    assert body["active"] is True


def test_policy_503_when_no_file_and_docs_unreachable(client, monkeypatch):
    monkeypatch.delenv("NEMOCLAW_POLICY_FILE", raising=False)
    # Point the docs fetch at an unroutable local port: fast failure, no network.
    monkeypatch.setattr(
        "ghostpanel.server.api._NEMOCLAW_DOCS_URL", "http://127.0.0.1:9/llms.txt"
    )
    resp = client.get("/policy")
    assert resp.status_code == 503
    assert "Refusing to fabricate" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# SwarmManager: voice assignment + insights.json (browserless stub runner)
# ---------------------------------------------------------------------------
async def test_swarm_assigns_voices_and_writes_insights(tmp_path):
    seen: list[list[str]] = []

    async def assigner(personas):  # noqa: ANN001
        seen.append([p.id for p in personas])
        return {p.id: f"voice-{p.id}" for p in personas}

    swarm, registry = _make_browserless_swarm(tmp_path, voice_assigner=assigner)
    run_id = await swarm.start_run(
        "http://target.test/", "sign up", ["grandma-72", "power-user"]
    )
    record = registry.get(run_id)
    await record.task_handle

    # assign_voices seam was invoked exactly once with the run's personas...
    assert seen == [["grandma-72", "power-user"]]
    # ...and the mapping landed on the (registry-visible) PersonaConfigs.
    assert {p.id: p.voice_id for p in record.personas} == {
        "grandma-72": "voice-grandma-72",
        "power-user": "voice-power-user",
    }

    # insights.json written next to report.html, matching the frozen wire format.
    import json

    insights = json.loads((tmp_path / run_id / "insights.json").read_text())
    assert insights["ghostpanel_score"] == 100  # stub runner: everyone succeeds
    assert "wcag_findings" in insights and "summary" in insights
    assert record.status == RunStatus.FINISHED


async def test_swarm_survives_voice_assigner_failure(tmp_path):
    async def assigner(personas):  # noqa: ANN001
        raise RuntimeError("no GRADIUM_API_KEY / catalog down")

    swarm, registry = _make_browserless_swarm(tmp_path, voice_assigner=assigner)
    run_id = await swarm.start_run("http://target.test/", "sign up", ["grandma-72"])
    record = registry.get(run_id)
    await record.task_handle  # must not raise

    assert record.status == RunStatus.FINISHED
    assert record.personas[0].voice_id is None  # defaults kept


async def test_assign_voices_never_overrides_explicit_voice_id(tmp_path):
    async def assigner(personas):  # noqa: ANN001
        return {p.id: "catalog-voice" for p in personas}

    swarm, _ = _make_browserless_swarm(tmp_path, voice_assigner=assigner)
    explicit = PersonaConfig(id="p-explicit", name="P", voice_id="hand-picked")
    fresh = PersonaConfig(id="p-fresh", name="Q")
    await swarm._assign_voices([explicit, fresh])
    assert explicit.voice_id == "hand-picked"
    assert fresh.voice_id == "catalog-voice"


async def test_swarm_survives_insights_failure(tmp_path, monkeypatch):
    def boom(report, personas):  # noqa: ANN001
        raise RuntimeError("insights exploded")

    monkeypatch.setattr("ghostpanel.server.swarm.build_insights", boom)
    swarm, registry = _make_browserless_swarm(tmp_path)
    run_id = await swarm.start_run("http://target.test/", "sign up", ["grandma-72"])
    record = registry.get(run_id)
    await record.task_handle  # must not raise

    assert record.status == RunStatus.FINISHED
    assert not (tmp_path / run_id / "insights.json").exists()
    # The HTML report is still written (plain call path).
    assert (tmp_path / run_id / "report.html").exists()
