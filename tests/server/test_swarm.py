"""SwarmManager + WebSocketHub/Sink tests — all stubs, no keys, no network."""

from __future__ import annotations

import asyncio

from ghostpanel_contracts import (
    EventSink,
    PersonaFinished,
    PersonaOutcome,
    PersonaStarted,
    RunFinished,
    RunStarted,
    StepEvent,
)

from ghostpanel.server.config import Settings
from ghostpanel.server.ws import WebSocketEventSink, WebSocketHub
from server_stubs import (
    CollectingEventSink,
    CrashingRunner,
    FailingVoice,
    RecordingVoice,
    make_swarm,
)

TARGET = "http://localhost:9999/hostile_form.html"
TASK = "Sign up for the newsletter"


async def _run(swarm) -> str:
    run_id = await swarm.start_run(TARGET, TASK, None)
    await swarm.wait_for_run(run_id)
    return run_id


async def test_two_personas_produce_report_and_event_sequence(tmp_path):
    swarm, sink = make_swarm(
        tmp_path, outcomes={"grandma-72": PersonaOutcome.STUCK}
    )
    run_id = await _run(swarm)

    # Report cached in the registry, completion_rate sane (1 of 2 succeeded).
    report = swarm.registry.get_report(run_id)
    assert report is not None
    assert report.run_id == run_id
    assert report.target_url == TARGET and report.task == TASK
    assert len(report.results) == 2
    assert 0.0 <= report.completion_rate <= 1.0
    assert report.completion_rate == 0.5
    assert report.generated_at != ""

    # Event sequence: RunStarted first, RunFinished last, persona lifecycle between.
    events = sink.events
    assert isinstance(events[0], RunStarted)
    assert {p.id for p in events[0].personas} == {"grandma-72", "tremor-45"}
    assert isinstance(events[-1], RunFinished)
    assert events[-1].report_url == f"/runs/{run_id}/report"
    assert events[-1].completion_rate == 0.5
    for pid in ("grandma-72", "tremor-45"):
        assert any(isinstance(e, PersonaStarted) and e.persona_id == pid for e in events)
        assert any(isinstance(e, StepEvent) and e.persona_id == pid for e in events)
        assert any(isinstance(e, PersonaFinished) and e.persona_id == pid for e in events)

    assert swarm.registry.get(run_id).status == "finished"


async def test_voice_called_only_for_non_success(tmp_path):
    voice = RecordingVoice()
    swarm, _ = make_swarm(
        tmp_path, outcomes={"grandma-72": PersonaOutcome.STEP_BUDGET}, voice=voice
    )
    await _run(swarm)
    assert voice.interviewed == ["grandma-72"]


async def test_voice_failure_does_not_break_run(tmp_path):
    swarm, sink = make_swarm(
        tmp_path, outcomes={"grandma-72": PersonaOutcome.STUCK}, voice=FailingVoice()
    )
    run_id = await _run(swarm)
    assert swarm.registry.get_report(run_id) is not None
    assert isinstance(sink.events[-1], RunFinished)


async def test_crashed_session_becomes_error_result(tmp_path):
    swarm, sink = make_swarm(
        tmp_path, runner_factory=lambda browser, artifact_dir: CrashingRunner()
    )
    run_id = await _run(swarm)
    report = swarm.registry.get_report(run_id)
    assert report is not None
    assert all(r.outcome is PersonaOutcome.ERROR for r in report.results)
    assert report.completion_rate == 0.0
    assert isinstance(sink.events[-1], RunFinished)


def test_sinks_satisfy_event_sink_protocol():
    hub = WebSocketHub()
    assert isinstance(WebSocketEventSink("run-1", hub), EventSink)
    assert isinstance(CollectingEventSink(), EventSink)


class _FakeSocket:
    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_json(self, data) -> None:
        self.received.append(data)


async def test_hub_replays_backlog_to_late_subscriber():
    hub = WebSocketHub()
    sink = WebSocketEventSink("run-1", hub)
    for step in range(3):
        await sink.emit(
            StepEvent(run_id="run-1", persona_id="p", step=step, caption=f"step {step}")
        )

    late = _FakeSocket()
    await hub.subscribe("run-1", late)
    assert [e["step"] for e in late.received] == [0, 1, 2]
    assert all(e["event"] == "step" for e in late.received)

    # Live events keep flowing after the replay...
    await sink.emit(StepEvent(run_id="run-1", persona_id="p", step=3, caption="step 3"))
    assert late.received[-1]["step"] == 3

    # ...and stop after unsubscribe.
    await hub.unsubscribe("run-1", late)
    await sink.emit(StepEvent(run_id="run-1", persona_id="p", step=4, caption="step 4"))
    assert late.received[-1]["step"] == 3


async def test_hub_safe_under_concurrent_emits():
    hub = WebSocketHub()
    ws = _FakeSocket()
    await hub.subscribe("run-1", ws)
    sink = WebSocketEventSink("run-1", hub)
    await asyncio.gather(
        *(
            sink.emit(StepEvent(run_id="run-1", persona_id=f"p{i}", step=i, caption="x"))
            for i in range(50)
        )
    )
    assert len(ws.received) == 50
    assert len(hub.buffer("run-1")) == 50


def test_settings_from_env_and_nemoclaw_override(monkeypatch):
    env = {
        "HAI_API_KEY": "hk-test",
        "HAI_BASE_URL": "https://api.hcompany.ai/v1/",
        "HAI_MODEL": "holo3-1-35b-a3b",
        "HAI_RPM": "5",
        "GRADIUM_API_KEY": "gd-test",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "GHOSTPANEL_HOST": "0.0.0.0",
        "GHOSTPANEL_PORT": "9001",
        "GHOSTPANEL_ARTIFACT_DIR": "/tmp/gp-artifacts",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("NEMOCLAW_GATEWAY_URL", "")

    settings = Settings.from_env(env_file=None)
    assert settings.hai_api_key == "hk-test"
    assert settings.hai_rpm == 5
    assert settings.gradium_api_key == "gd-test"
    assert settings.host == "0.0.0.0" and settings.port == 9001
    assert str(settings.artifact_dir) == "/tmp/gp-artifacts"
    # No gateway -> Holo is called directly.
    assert settings.holo_base_url == "https://api.hcompany.ai/v1/"

    # NEMOCLAW_GATEWAY_URL set -> inference is routed through the gateway.
    monkeypatch.setenv("NEMOCLAW_GATEWAY_URL", "http://127.0.0.1:7331/v1/")
    assert Settings.from_env(env_file=None).holo_base_url == "http://127.0.0.1:7331/v1/"
