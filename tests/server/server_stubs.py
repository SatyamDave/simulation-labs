"""Stub collaborators for Agent 3's tests.

The other modules (engine/runner/voice/report) do not exist on this branch —
these stubs satisfy the frozen Protocols so the swarm/API tests run with no
keys, no network and no browser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ghostpanel_contracts import (
    Action,
    ActionType,
    HeatPoint,
    Observation,
    PersonaConfig,
    PersonaFinished,
    PersonaOutcome,
    PersonaResult,
    PersonaStarted,
    RunReport,
    StepEvent,
    StepRecord,
    SurvivalPoint,
)
from pydantic import BaseModel

from ghostpanel.server.config import Settings
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub


class CollectingEventSink:
    """EventSink that just records every emitted RunEvent model."""

    def __init__(self) -> None:
        self.events: list[BaseModel] = []

    async def emit(self, event: BaseModel) -> None:
        self.events.append(event)


class StubHolo:
    """Never called by the stub runner; exists so agent wiring has a client."""

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        return (0, 0)

    async def navigate(self, image_png: bytes, task: str, history: list[str]) -> Action:
        return Action(type=ActionType.ANSWER, caption="stub answer")


class StubAgent:
    def __init__(self, persona: PersonaConfig, holo: Any) -> None:
        self.persona = persona
        self.holo = holo

    async def decide(self, obs: Observation, history: list[str]) -> Action:
        return Action(type=ActionType.ANSWER, caption="stub answer")


class StubRunner:
    """SessionRunner that fabricates a PersonaResult and emits the standard
    PersonaStarted -> StepEvent -> PersonaFinished sequence."""

    def __init__(
        self,
        browser: Any = None,
        artifact_dir: Any = None,
        outcomes: Optional[dict[str, PersonaOutcome]] = None,
    ) -> None:
        self.browser = browser
        self.artifact_dir = artifact_dir
        self.outcomes = outcomes or {}

    async def run(
        self,
        persona: PersonaConfig,
        agent: Any,
        target_url: str,
        task: str,
        sink: Any,
        run_id: str,
    ) -> PersonaResult:
        outcome = self.outcomes.get(persona.id, PersonaOutcome.SUCCESS)
        await sink.emit(PersonaStarted(run_id=run_id, persona_id=persona.id))
        action = Action(type=ActionType.CLICK, x=10, y=20, caption="Clicking Sign up")
        await sink.emit(
            StepEvent(
                run_id=run_id, persona_id=persona.id, step=0,
                caption=action.caption, x=action.x, y=action.y,
            )
        )
        failed = outcome is not PersonaOutcome.SUCCESS
        await sink.emit(
            PersonaFinished(
                run_id=run_id,
                persona_id=persona.id,
                outcome=outcome,
                failure_coords=(10, 20) if failed else None,
                failure_reason="gave up" if failed else "",
                steps_survived=1,
            )
        )
        return PersonaResult(
            persona_id=persona.id,
            outcome=outcome,
            steps=[StepRecord(persona_id=persona.id, step=0, action=action)],
            failure_coords=(10, 20) if failed else None,
            failure_step=0 if failed else None,
            failure_reason="gave up" if failed else "",
            duration_s=0.1,
        )


class CrashingRunner:
    """SessionRunner whose run() raises — models an infra failure."""

    async def run(self, persona, agent, target_url, task, sink, run_id):  # noqa: ANN001
        raise RuntimeError("browser exploded")


class StubReportBuilder:
    """ReportBuilder producing a minimal valid RunReport."""

    def build(
        self,
        run_id: str,
        target_url: str,
        task: str,
        results: list[PersonaResult],
        personas: list[PersonaConfig],
    ) -> RunReport:
        names = {p.id: p.name for p in personas}
        survival = [
            SurvivalPoint(
                persona_id=r.persona_id,
                persona_name=names.get(r.persona_id, ""),
                outcome=r.outcome,
                steps_survived=len(r.steps),
                completed=r.outcome is PersonaOutcome.SUCCESS,
            )
            for r in results
        ]
        heat = [
            HeatPoint(x=r.failure_coords[0], y=r.failure_coords[1], persona_id=r.persona_id)
            for r in results
            if r.failure_coords is not None
        ]
        completed = sum(1 for r in results if r.outcome is PersonaOutcome.SUCCESS)
        return RunReport(
            run_id=run_id,
            target_url=target_url,
            task=task,
            results=results,
            survival=survival,
            heatmap_points=heat,
            completion_rate=completed / len(results) if results else 0.0,
        )


class RecordingVoice:
    """VoiceEngine that records which personas got an exit interview."""

    def __init__(self) -> None:
        self.interviewed: list[str] = []

    async def exit_interview(self, result: PersonaResult, persona: PersonaConfig) -> str:
        self.interviewed.append(persona.id)
        return f"/tmp/{persona.id}.wav"

    async def mutter(self, text: str, voice_id: Optional[str]) -> str:
        return "/tmp/mutter.wav"


class FailingVoice(RecordingVoice):
    """VoiceEngine whose exit_interview always raises."""

    async def exit_interview(self, result: PersonaResult, persona: PersonaConfig) -> str:
        raise RuntimeError("gradium is down")


def make_personas() -> list[PersonaConfig]:
    return [
        PersonaConfig(id="grandma-72", name="Margaret, 72", blur_sigma=2.0),
        PersonaConfig(id="tremor-45", name="Dev, 45", tremor_sigma_px=6.0),
    ]


def make_swarm(
    tmp_path: Path,
    *,
    outcomes: Optional[dict[str, PersonaOutcome]] = None,
    sink: Optional[CollectingEventSink] = None,
    voice: Optional[RecordingVoice] = None,
    runner_factory: Any = None,
) -> tuple[SwarmManager, CollectingEventSink]:
    """A SwarmManager fully wired with stubs (every DI seam overridden)."""
    settings = Settings(artifact_dir=tmp_path / "artifacts")
    hub = WebSocketHub()
    registry = RunRegistry()
    collecting = sink if sink is not None else CollectingEventSink()
    swarm = SwarmManager(
        settings,
        hub,
        registry,
        persona_loader=lambda ids: make_personas(),
        holo_factory=lambda s: StubHolo(),
        agent_factory=StubAgent,
        runner_factory=runner_factory
        or (lambda browser, artifact_dir: StubRunner(browser, artifact_dir, outcomes)),
        report_builder_factory=StubReportBuilder,
        voice_factory=lambda s: voice,
        sink_factory=lambda run_id: collecting,
    )
    return swarm, collecting
