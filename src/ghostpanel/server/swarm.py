"""SwarmManager — runs N persona sessions in parallel over one shared browser +
one shared rate-limited Holo client, streams live events, and on completion builds
the report and triggers voice exit-interviews.

This is orchestration only: every concrete class it wires (persona agent, session
runner, report builder, voice engine) is injected by the composition root
(``app.create_app``) or the tests. Factories are used so the wiring is swappable —
tests pass a ``FakeHoloClient`` + real ``PlaywrightSessionRunner``, or a stub
runner to exercise the per-persona error guard, without touching this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from ghostpanel_contracts import (
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    RunFinished,
    RunReport,
    RunStarted,
)

from ghostpanel.engine.persona_agent import HoloPersonaAgent
from ghostpanel.engine.personas import load_personas
from ghostpanel.report.builder import SurvivalReportBuilder
from ghostpanel.report import write_deliverable_report
from ghostpanel.report.insights import build_insights
from ghostpanel.runner.policy import RequestPolicy
from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.voice.narrate import write_exit_interview

from .runs import RunRegistry
from .ws import WebSocketEventSink, WebSocketHub

# Type aliases for the injectable factories.
AgentFactory = Callable[[PersonaConfig, Any, str], Any]
RunnerFactory = Callable[[Any, Path, Optional[Callable]], Any]
PredicateFactory = Callable[[str], Optional[Callable]]
# (run_artifact_dir) -> VoiceEngine
VoiceEngineFactory = Callable[[Path], Any]
# (personas) -> {persona_id: gradium voice_id} — see ghostpanel.voice.voices.assign_voices
VoiceAssigner = Callable[[list[PersonaConfig]], Awaitable[dict[str, str]]]

logger = logging.getLogger(__name__)


def _default_agent_factory(persona: PersonaConfig, holo: Any, task: str) -> Any:
    return HoloPersonaAgent(persona, holo, task=task)


def _default_runner_factory(
    browser: Any, artifact_dir: Path, predicate: Optional[Callable]
) -> Any:
    return PlaywrightSessionRunner(browser, artifact_dir, success_predicate=predicate)


def _default_predicate_factory(target_url: str) -> Optional[Callable]:
    """The bundled demo pages declare success when a success element renders.

    hostile_form.html (and the fixed variant via ``?as=``) and payment_form.html
    reveal ``#ok``; demo_signup.html reveals ``#done`` ("You're in!"). The
    predicate is page-VERIFIED success: it stops a policy-caged persona from
    claiming a payment that never left the machine, AND — critically for the
    signup demo — it makes the undegraded probe's completion depend on the page
    actually reaching the confirmation, not on the model volunteering answer().
    A persona that hallucinates answer() before the page is done does NOT pass."""
    # Match on the path OR the raw URL — the fixed-form rerun opts in via a
    # ``?as=hostile_form.html`` query suffix (http.server ignores the query).
    path = target_url.split("?", 1)[0].rstrip("/")
    candidates = (path, target_url.rstrip("/"))
    if any(c.endswith(("hostile_form.html", "payment_form.html")) for c in candidates):
        async def _ok(page) -> bool:  # noqa: ANN001
            return await page.locator("#ok").is_visible()

        return _ok
    if any(c.endswith("demo_signup.html") for c in candidates):
        async def _done(page) -> bool:  # noqa: ANN001
            return await page.locator("#done").is_visible()

        return _done
    return None


class SwarmManager:
    """Starts + drives runs. One instance per app; holds shared browser + client."""

    def __init__(
        self,
        *,
        browser: Any,
        holo_client: Any,
        hub: WebSocketHub,
        registry: RunRegistry,
        artifact_dir: str | Path,
        report_builder: Optional[SurvivalReportBuilder] = None,
        anthropic_key: Optional[str] = None,
        voice_engine_factory: Optional[VoiceEngineFactory] = None,
        voice_assigner: Optional[VoiceAssigner] = None,
        voice_success_ids: Optional[set[str]] = None,
        request_policy: Optional[RequestPolicy] = None,
        agent_factory: AgentFactory = _default_agent_factory,
        runner_factory: RunnerFactory = _default_runner_factory,
        predicate_factory: PredicateFactory = _default_predicate_factory,
    ) -> None:
        self.browser = browser
        self.holo_client = holo_client
        self.hub = hub
        self.registry = registry
        self.artifact_dir = Path(artifact_dir)
        self.report_builder = report_builder or SurvivalReportBuilder()
        self.anthropic_key = anthropic_key or None
        self.voice_engine_factory = voice_engine_factory
        self.voice_assigner = voice_assigner
        # Personas that still get a voice interview even on success (e.g. ai-agent).
        self.voice_success_ids = voice_success_ids or {"ai-agent"}
        self.agent_factory = agent_factory
        # NemoClaw-mirror request policy (browse-only): when set and the caller
        # kept the default runner factory, every runner is built with it so
        # denied requests (POST/PUT/DELETE…) abort inside the browser context.
        self.request_policy = request_policy
        if request_policy is not None and runner_factory is _default_runner_factory:
            def runner_factory(  # noqa: ANN202 - matches RunnerFactory
                browser: Any, artifact_dir: Path, predicate: Optional[Callable]
            ) -> Any:
                return PlaywrightSessionRunner(
                    browser,
                    artifact_dir,
                    success_predicate=predicate,
                    policy=request_policy,
                )
        self.runner_factory = runner_factory
        self.predicate_factory = predicate_factory

    # -- public API -------------------------------------------------------
    async def start_run(
        self,
        target_url: str,
        task: str,
        persona_ids: Optional[list[str]] = None,
    ) -> str:
        """Register a run, kick it off in the background, return its ``run_id``.

        The heavy work runs in an asyncio task stored on the RunRecord so callers
        (tests, shutdown) can ``await record.task_handle`` if they want to block.
        """
        run_id = uuid.uuid4().hex[:12]
        personas = load_personas(persona_ids)
        if not personas:
            # Unknown/empty ids -> fall back to the full roster so a run is never empty.
            personas = load_personas(None)

        record = self.registry.create(
            run_id, target_url, task, [p.id for p in personas]
        )
        # Same objects the run mutates (voice assignment), so /ask sees voice_ids.
        record.personas = personas
        record.task_handle = asyncio.create_task(
            self._execute(run_id, target_url, task, personas)
        )
        return run_id

    # -- internals --------------------------------------------------------
    async def _execute(
        self,
        run_id: str,
        target_url: str,
        task: str,
        personas: list[PersonaConfig],
    ) -> RunReport:
        run_sink = WebSocketEventSink(run_id, self.hub)
        try:
            await run_sink.emit(
                RunStarted(
                    run_id=run_id,
                    target_url=target_url,
                    task=task,
                    personas=personas,
                )
            )

            # Give each persona a distinct Gradium voice up front (guarded; voice
            # trouble must never break a run).
            await self._assign_voices(personas)

            # Best-effort clean screenshot of the target (1280x800) so the report can
            # overlay the abandonment heatmap on the REAL page. Never breaks the run.
            await self._capture_target(run_id, target_url)

            predicate = self.predicate_factory(target_url)
            results: list[PersonaResult] = await asyncio.gather(
                *(
                    self._run_one(run_id, persona, target_url, task, predicate)
                    for persona in personas
                )
            )

            report = self.report_builder.build(
                run_id, target_url, task, list(results), personas
            )

            # Fill exit-interview narration (mutates the PersonaResults in-place, so
            # the change is reflected in the report + the HTML we write next).
            await self._narrate(run_id, report, personas)

            insights = self._write_insights(run_id, report, personas)

            try:
                # insights=None (a guarded failure above) lets the renderer
                # recompute its own from the personas we hand it.
                write_deliverable_report(
                    report, self.artifact_dir, insights=insights, personas=personas
                )
            except Exception:  # noqa: BLE001 - a report render hiccup must not kill the run
                pass

            self.registry.set_report(run_id, report)

            await run_sink.emit(
                RunFinished(
                    run_id=run_id,
                    report_url=f"/artifacts/{run_id}/report.html",
                    completion_rate=report.completion_rate,
                )
            )
            return report
        except Exception as exc:  # noqa: BLE001 - never let a run crash the server
            self.registry.set_error(run_id, f"{type(exc).__name__}: {exc}"[:300])
            try:
                await run_sink.emit(
                    RunFinished(
                        run_id=run_id,
                        report_url=f"/artifacts/{run_id}/report.html",
                        completion_rate=0.0,
                    )
                )
            except Exception:  # noqa: BLE001
                pass
            raise

    async def _assign_voices(self, personas: list[PersonaConfig]) -> None:
        """Resolve a distinct Gradium voice per persona (mutates ``voice_id`` in
        place). Fully guarded: no assigner / any failure -> log and keep defaults.
        Explicit ``voice_id`` values from personas/*.json are never overridden."""
        if self.voice_assigner is None:
            return
        try:
            mapping = await self.voice_assigner(personas)
        except Exception as exc:  # noqa: BLE001 - voice trouble never breaks a run
            logger.warning("Voice assignment failed; using default voices: %s", exc)
            return
        for persona in personas:
            assigned = (mapping or {}).get(persona.id)
            if assigned and not persona.voice_id:
                persona.voice_id = assigned

    def _write_insights(
        self,
        run_id: str,
        report: RunReport,
        personas: list[PersonaConfig],
    ) -> Optional[dict]:
        """Compute insights and persist ``<artifact_dir>/<run_id>/insights.json``.
        Guarded: an insights failure never breaks the run (returns None)."""
        try:
            insights = build_insights(report, personas)
            run_dir = self.artifact_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "insights.json").write_text(
                json.dumps(insights, indent=2), encoding="utf-8"
            )
            return insights
        except Exception as exc:  # noqa: BLE001 - insights are best-effort
            logger.warning("Insights generation failed for run %s: %s", run_id, exc)
            return None

    async def _capture_target(self, run_id: str, target_url: str) -> None:
        """Open the target in a fresh context and save a clean 1280x800 screenshot to
        ``<artifact_dir>/<run_id>/target.png`` for the report heatmap overlay. Purely
        best-effort — any failure (bad URL, launch_browser=False in tests) is swallowed."""
        if self.browser is None:
            return
        context = None
        try:
            run_dir = self.artifact_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(600)
            await page.screenshot(path=str(run_dir / "target.png"))
        except Exception:  # noqa: BLE001
            pass
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:  # noqa: BLE001
                    pass

    async def _run_one(
        self,
        run_id: str,
        persona: PersonaConfig,
        target_url: str,
        task: str,
        predicate: Optional[Callable],
    ) -> PersonaResult:
        """Run one persona; convert any hard failure into an ERROR PersonaResult so
        a single crash never poisons ``asyncio.gather`` for the rest of the swarm."""
        sink = WebSocketEventSink(run_id, self.hub)
        try:
            agent = self.agent_factory(persona, self.holo_client, task)
            runner = self.runner_factory(self.browser, self.artifact_dir, predicate)
            return await runner.run(persona, agent, target_url, task, sink, run_id)
        except Exception as exc:  # noqa: BLE001
            return PersonaResult(
                persona_id=persona.id,
                outcome=PersonaOutcome.ERROR,
                failure_reason=f"{type(exc).__name__}: {exc}"[:200],
            )

    async def _narrate(
        self,
        run_id: str,
        report: RunReport,
        personas: list[PersonaConfig],
    ) -> None:
        """Attach exit-interview text (always) + Gradium audio (when configured) to
        non-success personas. Each call is guarded so one voice failure never breaks
        the run or blocks the others."""
        persona_by_id = {p.id: p for p in personas}
        run_dir = self.artifact_dir / run_id
        voice_engine = None
        if self.voice_engine_factory is not None:
            try:
                voice_engine = self.voice_engine_factory(run_dir)
            except Exception:  # noqa: BLE001
                voice_engine = None

        for result in report.results:
            persona = persona_by_id.get(result.persona_id)
            if persona is None:
                continue
            is_success = result.outcome == PersonaOutcome.SUCCESS
            if is_success and persona.id not in self.voice_success_ids:
                continue

            audio_done = False
            if voice_engine is not None:
                try:
                    await voice_engine.exit_interview(result, persona)
                    audio_done = True  # also sets transcript + audio_path
                except Exception:  # noqa: BLE001 - fall back to text-only narration
                    audio_done = False
            if not audio_done:
                try:
                    result.transcript = await write_exit_interview(
                        result, persona, anthropic_key=self.anthropic_key
                    )
                except Exception:  # noqa: BLE001
                    pass
