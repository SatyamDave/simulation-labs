"""SwarmManager — launches N persona sessions in parallel and aggregates them.

This is (together with app.py) the composition root: the ONLY place concrete
classes from engine/runner/report/voice are referenced — and only via *lazy*
imports inside the default factories below, so this module imports cleanly on
a branch where those modules do not exist yet. Every collaborator is an
injectable seam; tests swap in stubs and never touch the network.

Dependency-injection seams (constructor kwargs, all optional):
  persona_loader(ids)                 -> list[PersonaConfig]   (engine.personas.load_personas)
  holo_factory(settings)              -> HoloClient            (LiveHoloClient — ONE shared,
                                                                rate-limited client per manager)
  agent_factory(persona, holo)        -> PersonaAgent          (HoloPersonaAgent)
  runner_factory(browser, artifact_dir) -> SessionRunner       (PlaywrightSessionRunner)
  report_builder_factory()            -> ReportBuilder         (SurvivalReportBuilder)
  voice_factory(settings)             -> VoiceEngine | None    (GradiumVoiceEngine)
  sink_factory(run_id)                -> EventSink             (WebSocketEventSink)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ghostpanel_contracts import (
    EventSink,
    HoloClient,
    PersonaAgent,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    ReportBuilder,
    RunFinished,
    RunStarted,
    SessionRunner,
    VoiceEngine,
)

from ghostpanel.server.config import Settings
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.ws import WebSocketEventSink, WebSocketHub

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Default factories — lazy imports of the concrete registry classes. These
# run at CALL time (first run), never at module import time.
# --------------------------------------------------------------------------
def _default_persona_loader(ids: Optional[list[str]]) -> list[PersonaConfig]:
    from ghostpanel.engine.personas import load_personas

    return load_personas(ids=ids)


def _default_holo_factory(settings: Settings) -> HoloClient:
    from ghostpanel.engine.holo_client import LiveHoloClient

    return LiveHoloClient(
        settings.hai_api_key,
        settings.holo_base_url,  # NEMOCLAW_GATEWAY_URL override applies here
        settings.hai_model,
        settings.hai_rpm,
    )


def _default_agent_factory(persona: PersonaConfig, holo: HoloClient) -> PersonaAgent:
    from ghostpanel.engine.persona_agent import HoloPersonaAgent

    return HoloPersonaAgent(persona, holo)


def _default_runner_factory(browser: Any, artifact_dir: Any) -> SessionRunner:
    from ghostpanel.runner.session import PlaywrightSessionRunner

    return PlaywrightSessionRunner(browser, artifact_dir)


def _default_report_builder_factory() -> ReportBuilder:
    from ghostpanel.report.builder import SurvivalReportBuilder

    return SurvivalReportBuilder()


def _default_voice_factory(settings: Settings) -> Optional[VoiceEngine]:
    if not settings.gradium_api_key:
        return None
    from ghostpanel.voice.gradium_voice import GradiumVoiceEngine

    return GradiumVoiceEngine(
        settings.gradium_api_key,
        str(settings.artifact_dir),
        anthropic_key=settings.anthropic_api_key or None,
    )


class SwarmManager:
    """Runs the persona swarm for a target URL + task and aggregates results."""

    def __init__(
        self,
        settings: Settings,
        hub: WebSocketHub,
        registry: RunRegistry,
        *,
        browser: Any = None,  # shared Playwright Browser, set by app lifespan
        persona_loader: Callable[[Optional[list[str]]], list[PersonaConfig]] | None = None,
        holo_factory: Callable[[Settings], HoloClient] | None = None,
        agent_factory: Callable[[PersonaConfig, HoloClient], PersonaAgent] | None = None,
        runner_factory: Callable[[Any, Any], SessionRunner] | None = None,
        report_builder_factory: Callable[[], ReportBuilder] | None = None,
        voice_factory: Callable[[Settings], Optional[VoiceEngine]] | None = None,
        sink_factory: Callable[[str], EventSink] | None = None,
    ) -> None:
        self.settings = settings
        self.hub = hub
        self.registry = registry
        self.browser = browser

        self._persona_loader = persona_loader or _default_persona_loader
        self._holo_factory = holo_factory or _default_holo_factory
        self._agent_factory = agent_factory or _default_agent_factory
        self._runner_factory = runner_factory or _default_runner_factory
        self._report_builder_factory = report_builder_factory or _default_report_builder_factory
        self._voice_factory = voice_factory or _default_voice_factory
        self._sink_factory = sink_factory or (lambda run_id: WebSocketEventSink(run_id, hub))

        self._holo: Optional[HoloClient] = None  # ONE shared client for the whole swarm
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # -- public API ---------------------------------------------------------
    async def start_run(
        self,
        target_url: str,
        task: str,
        persona_ids: Optional[list[str]] = None,
    ) -> str:
        """Register a run and launch it in the background; returns run_id."""
        run_id = uuid.uuid4().hex[:12]
        self.registry.create(run_id, target_url, task)
        bg = asyncio.create_task(
            self._execute_run(run_id, target_url, task, persona_ids),
            name=f"ghostpanel-run-{run_id}",
        )
        self._tasks[run_id] = bg
        bg.add_done_callback(lambda _t: self._tasks.pop(run_id, None))
        return run_id

    async def wait_for_run(self, run_id: str) -> None:
        """Block until a started run has fully settled (tests / clean shutdown)."""
        bg = self._tasks.get(run_id)
        if bg is not None:
            await bg

    async def shutdown(self) -> None:
        """Cancel any in-flight runs (app shutdown)."""
        for bg in list(self._tasks.values()):
            bg.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    # -- internals ----------------------------------------------------------
    def _shared_holo(self) -> HoloClient:
        if self._holo is None:
            self._holo = self._holo_factory(self.settings)
        return self._holo

    async def _execute_run(
        self,
        run_id: str,
        target_url: str,
        task: str,
        persona_ids: Optional[list[str]],
    ) -> None:
        sink = self._sink_factory(run_id)
        try:
            personas = self._persona_loader(persona_ids)
            await sink.emit(
                RunStarted(run_id=run_id, target_url=target_url, task=task, personas=personas)
            )

            holo = self._shared_holo()
            artifact_dir = self.settings.artifact_dir / run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)

            async def _one_session(persona: PersonaConfig) -> PersonaResult:
                agent = self._agent_factory(persona, holo)
                runner = self._runner_factory(self.browser, artifact_dir)
                return await runner.run(persona, agent, target_url, task, sink, run_id)

            settled = await asyncio.gather(
                *(_one_session(p) for p in personas), return_exceptions=True
            )
            results: list[PersonaResult] = []
            for persona, outcome in zip(personas, settled):
                if isinstance(outcome, BaseException):
                    logger.exception(
                        "persona %s session crashed", persona.id, exc_info=outcome
                    )
                    results.append(
                        PersonaResult(
                            persona_id=persona.id,
                            outcome=PersonaOutcome.ERROR,
                            failure_reason=f"session crashed: {outcome}",
                        )
                    )
                else:
                    results.append(outcome)

            report = self._report_builder_factory().build(
                run_id, target_url, task, results, personas
            )
            if not report.generated_at:
                report.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            await self._run_exit_interviews(results, personas)

            self.registry.set_report(run_id, report)
            await sink.emit(
                RunFinished(
                    run_id=run_id,
                    report_url=f"/runs/{run_id}/report",
                    completion_rate=report.completion_rate,
                )
            )
        except Exception:
            logger.exception("run %s failed", run_id)
            self.registry.set_failed(run_id)
            raise

    async def _run_exit_interviews(
        self, results: list[PersonaResult], personas: list[PersonaConfig]
    ) -> None:
        """Voice exit-interviews for every non-success persona. Voice failures
        (missing key, network, SDK errors) are logged and swallowed — they must
        never break the run or the report."""
        try:
            voice = self._voice_factory(self.settings)
        except Exception:
            logger.exception("voice engine construction failed; skipping exit interviews")
            return
        if voice is None:
            return
        personas_by_id = {p.id: p for p in personas}
        for result in results:
            if result.outcome == PersonaOutcome.SUCCESS:
                continue
            persona = personas_by_id.get(result.persona_id)
            if persona is None:
                continue
            try:
                await voice.exit_interview(result, persona)
            except Exception:
                logger.exception("exit interview failed for persona %s", result.persona_id)
