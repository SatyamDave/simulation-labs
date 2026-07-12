"""PlaywrightSessionRunner — drives ONE persona's browser session end to end.

Implements the ``SessionRunner`` contract: given a persona, a PersonaAgent, a
target URL, a task, an EventSink and a run id, it opens an isolated browser
context (with video recording), runs the perceive -> decide -> execute loop,
streams a ``StepEvent`` on every step, and returns a complete ``PersonaResult``.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

from ghostpanel_contracts import (
    ActionType,
    EventSink,
    Observation,
    PersonaAgent,
    PersonaConfig,
    PersonaFinished,
    PersonaOutcome,
    PersonaResult,
    PersonaStarted,
    StepEvent,
    StepRecord,
)

from ghostpanel.runner.detect import SuccessPredicate, is_stuck, is_success
from ghostpanel.runner.execute import execute_action
from ghostpanel.runner.thumbnail import to_thumb_data_uri

#: How many identical consecutive captions mean the persona is looping.
STUCK_WINDOW = 3


class PlaywrightSessionRunner:
    """Runs one persona session against a shared Playwright ``Browser``.

    Agent 3 constructs this with ``(browser, artifact_dir)`` per the registry.
    ``success_predicate`` optionally overrides the default success heuristic
    in :mod:`ghostpanel.runner.detect` (sync or async ``Page -> bool``).
    """

    def __init__(
        self,
        browser: Browser,
        artifact_dir: str | Path,
        success_predicate: Optional[SuccessPredicate] = None,
    ) -> None:
        self._browser = browser
        self._artifact_dir = Path(artifact_dir)
        self._success_predicate = success_predicate

    async def run(
        self,
        persona: PersonaConfig,
        agent: PersonaAgent,
        target_url: str,
        task: str,
        sink: EventSink,
        run_id: str,
    ) -> PersonaResult:
        started = time.monotonic()
        steps: list[StepRecord] = []
        # Frozen cross-agent convention: history[0] is the task; every later
        # entry is an executed action's caption.
        history: list[str] = [f"TASK: {task}"]
        outcome = PersonaOutcome.ERROR
        failure_reason = ""
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        video_dir = self._artifact_dir / run_id
        video_dir.mkdir(parents=True, exist_ok=True)
        viewport = persona.viewport.model_dump()

        try:
            context = await self._browser.new_context(
                viewport=viewport,
                record_video_dir=str(video_dir),
                record_video_size=viewport,
            )
            page = await context.new_page()
            await page.goto(target_url)
            await sink.emit(PersonaStarted(run_id=run_id, persona_id=persona.id))
            try:
                outcome, failure_reason = await asyncio.wait_for(
                    self._loop(page, persona, agent, target_url, sink, run_id, history, steps),
                    timeout=persona.deadline_s,
                )
            except asyncio.TimeoutError:
                outcome = PersonaOutcome.TIME_BUDGET
                failure_reason = f"time budget of {persona.deadline_s:g}s exhausted"
        except Exception as exc:  # infra failure, not a real "abandon"
            outcome = PersonaOutcome.ERROR
            failure_reason = f"{type(exc).__name__}: {exc}"

        video_path = await self._close_and_save_video(context, page, video_dir, persona.id)

        failure_coords: Optional[tuple[int, int]] = None
        failure_step: Optional[int] = None
        if outcome is not PersonaOutcome.SUCCESS and steps:
            failure_coords, failure_step = _last_meaningful(steps)

        await sink.emit(
            PersonaFinished(
                run_id=run_id,
                persona_id=persona.id,
                outcome=outcome,
                failure_coords=failure_coords,
                failure_reason=failure_reason,
                steps_survived=len(steps),
            )
        )
        return PersonaResult(
            persona_id=persona.id,
            outcome=outcome,
            steps=steps,
            failure_coords=failure_coords,
            failure_step=failure_step,
            failure_reason=failure_reason,
            duration_s=time.monotonic() - started,
            video_path=video_path,
        )

    async def _loop(
        self,
        page: Page,
        persona: PersonaConfig,
        agent: PersonaAgent,
        target_url: str,
        sink: EventSink,
        run_id: str,
        history: list[str],
        steps: list[StepRecord],
    ) -> tuple[PersonaOutcome, str]:
        """perceive -> decide -> record/emit -> check -> execute, per step."""
        for step_index in range(persona.max_steps):
            png = await page.screenshot()
            obs = Observation(
                raw_png=png,
                viewport=persona.viewport,
                step_index=step_index,
                url=page.url,
            )
            t0 = time.monotonic()
            action = await agent.decide(obs, history)
            latency_ms = int((time.monotonic() - t0) * 1000)

            thumb = to_thumb_data_uri(png)
            steps.append(
                StepRecord(
                    persona_id=persona.id,
                    step=step_index,
                    action=action,
                    thumbnail_b64=thumb,
                    latency_ms=latency_ms,
                )
            )
            # Emit on EVERY step — this powers the live grid.
            await sink.emit(
                StepEvent(
                    run_id=run_id,
                    persona_id=persona.id,
                    step=step_index,
                    caption=action.caption,
                    thumbnail_b64=thumb,
                    x=action.x,
                    y=action.y,
                )
            )

            if action.type is ActionType.ANSWER or await is_success(
                page, self._success_predicate
            ):
                return PersonaOutcome.SUCCESS, ""
            if is_stuck(history, window=STUCK_WINDOW):
                return (
                    PersonaOutcome.STUCK,
                    f"no progress: repeated '{history[-1]}' {STUCK_WINDOW}x",
                )

            await execute_action(page, action, target_url=target_url)
            history.append(action.caption)

        return PersonaOutcome.STEP_BUDGET, f"step budget of {persona.max_steps} exhausted"

    @staticmethod
    async def _close_and_save_video(
        context: Optional[BrowserContext],
        page: Optional[Page],
        video_dir: Path,
        persona_id: str,
    ) -> Optional[str]:
        """Close the context (flushes the recording) and save a named .webm."""
        if context is None:
            return None
        try:
            await context.close()
        except Exception:
            return None
        if page is None or page.video is None:
            return None
        try:
            named = video_dir / f"{persona_id}.webm"
            await page.video.save_as(named)
            try:
                await page.video.delete()  # drop the auto-named temp recording
            except Exception:
                pass
            return str(named)
        except Exception:
            return None


def _last_meaningful(steps: list[StepRecord]) -> tuple[Optional[tuple[int, int]], int]:
    """Coords + step index of the last step that targeted a pixel (else last step)."""
    for rec in reversed(steps):
        if rec.action.x is not None and rec.action.y is not None:
            return (rec.action.x, rec.action.y), rec.step
    return None, steps[-1].step
