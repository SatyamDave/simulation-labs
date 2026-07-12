"""PlaywrightSessionRunner — drives ONE persona's browser session end to end.

Registry: ghostpanel.runner.session.PlaywrightSessionRunner(browser, artifact_dir).
Agent 3 launches a single Chromium `Browser` once and shares it; this runner creates
one browser CONTEXT per session (cheap, isolated), records a video, runs the
perceive -> decide -> execute loop, streams StepEvents, and returns a PersonaResult.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from ghostpanel_contracts import (
    Action,
    ActionType,
    Observation,
    PersonaConfig,
    PersonaFinished,
    PersonaOutcome,
    PersonaResult,
    PersonaStarted,
    StepEvent,
    StepRecord,
)

from .detect import SuccessPredicate, is_stuck, is_success
from .execute import execute_action
from .policy import RequestPolicy
from .thumbnail import to_thumb_data_uri

# EXACT StepRecord.note for a policy-denied request. The report module counts
# blocked actions with `note == "policy_blocked"` (strict equality — see
# ghostpanel.report.insights.POLICY_BLOCKED_NOTE), so nothing may be appended;
# the blocked METHOD + host travel in the 🛡 StepEvent caption instead.
_POLICY_BLOCKED_NOTE = "policy_blocked"


def _default_caption(action: Action) -> str:
    """A human caption for the UI tile when the agent didn't supply one."""
    t = action.type
    if t == ActionType.CLICK:
        return f"clicking ({action.x}, {action.y})"
    if t == ActionType.WRITE:
        return f"typing '{(action.text or '')[:24]}'"
    if t == ActionType.SCROLL:
        return f"scrolling {action.direction.value if action.direction else 'down'}"
    if t == ActionType.GOTO:
        return f"going to {action.url}"
    if t == ActionType.WAIT:
        return "waiting"
    if t == ActionType.ANSWER:
        return "done"
    return t.value


_REASONS = {
    PersonaOutcome.STEP_BUDGET: "ran out of steps",
    PersonaOutcome.TIME_BUDGET: "ran out of time",
    PersonaOutcome.STUCK: "stuck in a loop",
    PersonaOutcome.ERROR: "session error",
}


class PlaywrightSessionRunner:
    """Concrete `SessionRunner`. Holds a shared Browser + an artifact directory.

    A per-run success predicate can be supplied at construction time; Agent 3 can
    construct one runner per predicate (they're cheap) or rely on the conservative
    default heuristic in `detect.is_success`.
    """

    def __init__(
        self,
        browser,
        artifact_dir,
        success_predicate: Optional[SuccessPredicate] = None,
        *,
        policy: Optional[RequestPolicy] = None,
    ) -> None:
        self.browser = browser
        self.artifact_dir = Path(artifact_dir)
        self.success_predicate = success_predicate
        # Optional NemoClaw-mirror request policy: when set, every browser
        # request the policy denies is ABORTED at the context level.
        self.policy = policy

    async def run(
        self,
        persona: PersonaConfig,
        agent,  # PersonaAgent
        target_url: str,
        task: str,
        sink,  # EventSink
        run_id: str,
    ) -> PersonaResult:
        start = time.monotonic()
        steps: list[StepRecord] = []
        history: list[str] = []

        # Mutable holders so partial state survives a wait_for cancellation.
        state = {
            "outcome": None,
            "failure_coords": None,
            "failure_step": None,
            "failure_reason": "",
            "current_step": 0,  # read by the policy route handler
        }

        video_dir = self.artifact_dir / run_id
        video_dir.mkdir(parents=True, exist_ok=True)
        viewport = persona.viewport.model_dump()

        context = await self.browser.new_context(
            viewport=viewport,
            record_video_dir=str(video_dir),
            record_video_size=viewport,
        )
        page = await context.new_page()
        video = None

        # --- NemoClaw-mirror policy enforcement (see runner.policy) --------
        if self.policy is not None:
            policy = self.policy
            shield_emitted: set[int] = set()  # steps that already got a 🛡 event

            async def _enforce(route) -> None:
                """Abort any request the policy denies. Fully guarded — policy
                enforcement must never crash the session."""
                req = route.request
                allowed = True
                try:
                    allowed = policy.allows(req.method, req.url)
                except Exception:  # noqa: BLE001
                    allowed = False  # fail closed: a broken policy engine is not a bypass
                try:
                    if allowed:
                        await route.continue_()
                        return
                    await route.abort("blockedbyclient")
                except Exception:  # noqa: BLE001 - context tearing down mid-flight
                    return
                # Record the block against the current step (best-effort).
                try:
                    step = state["current_step"]
                    method = req.method.upper()
                    if steps and not steps[-1].note:
                        steps[-1].note = _POLICY_BLOCKED_NOTE
                    if step not in shield_emitted:
                        shield_emitted.add(step)
                        host = urlsplit(req.url).hostname or ""
                        await sink.emit(
                            StepEvent(
                                run_id=run_id,
                                persona_id=persona.id,
                                step=step,
                                caption=f"🛡 Policy blocked {method} {host}",
                            )
                        )
                except Exception:  # noqa: BLE001 - recording must not break the session
                    pass

            await context.route("**/*", _enforce)

        async def _loop() -> None:
            for step in range(persona.max_steps):
                state["current_step"] = step
                png = await page.screenshot()
                obs = Observation(
                    raw_png=png,
                    viewport=persona.viewport,
                    step_index=step,
                    url=page.url,
                )
                decide_t0 = time.perf_counter()
                action = await agent.decide(obs, history)
                latency_ms = int((time.perf_counter() - decide_t0) * 1000)
                caption = action.caption or _default_caption(action)
                thumb = to_thumb_data_uri(png)

                steps.append(
                    StepRecord(
                        persona_id=persona.id,
                        step=step,
                        action=action,
                        thumbnail_b64=thumb,
                        latency_ms=latency_ms,
                    )
                )
                await sink.emit(
                    StepEvent(
                        run_id=run_id,
                        persona_id=persona.id,
                        step=step,
                        caption=caption,
                        thumbnail_b64=thumb,
                        x=action.x,
                        y=action.y,
                    )
                )

                # --- terminal checks (against the frame we just observed) ---
                if action.type == ActionType.ANSWER:
                    # "Receipts, not vibes": when a success predicate exists, a
                    # claimed completion must be VERIFIED by it. An agent whose
                    # payment was policy-blocked will happily answer "done" —
                    # that must not count as success.
                    if self.success_predicate is None or await is_success(
                        page, self.success_predicate
                    ):
                        state["outcome"] = PersonaOutcome.SUCCESS
                        return
                    if steps and not steps[-1].note:
                        steps[-1].note = "answer_unverified"
                    history.append(caption)
                    if is_stuck(history):
                        state["outcome"] = PersonaOutcome.STUCK
                        state["failure_step"] = step
                        state["failure_reason"] = (
                            "claimed the task was done, but the success signal "
                            "never appeared"
                        )
                        return
                    continue
                if await is_success(page, self.success_predicate):
                    state["outcome"] = PersonaOutcome.SUCCESS
                    return
                if is_stuck(history):
                    state["outcome"] = PersonaOutcome.STUCK
                    if action.x is not None and action.y is not None:
                        state["failure_coords"] = (action.x, action.y)
                    state["failure_step"] = step
                    state["failure_reason"] = f"repeated action: {caption}"
                    return

                # --- actuate ---
                exec_action = action
                if action.type == ActionType.RESTART:
                    exec_action = action.model_copy(update={"url": target_url})
                await execute_action(page, exec_action)
                history.append(caption)

            state["outcome"] = PersonaOutcome.STEP_BUDGET

        try:
            await page.goto(target_url)
            video = page.video
            await sink.emit(PersonaStarted(run_id=run_id, persona_id=persona.id))
            try:
                await asyncio.wait_for(_loop(), timeout=persona.deadline_s)
            except asyncio.TimeoutError:
                state["outcome"] = PersonaOutcome.TIME_BUDGET
        except Exception as exc:  # infra failure — not a real "abandon"
            state["outcome"] = PersonaOutcome.ERROR
            state["failure_reason"] = f"{type(exc).__name__}: {exc}"[:200]
        finally:
            # For a non-success terminal outcome, remember where it died.
            outcome = state["outcome"] or PersonaOutcome.ERROR
            if outcome != PersonaOutcome.SUCCESS and steps:
                last = steps[-1].action
                if state["failure_coords"] is None and last.x is not None and last.y is not None:
                    state["failure_coords"] = (last.x, last.y)
                if state["failure_step"] is None:
                    state["failure_step"] = steps[-1].step
                if not state["failure_reason"]:
                    state["failure_reason"] = _REASONS.get(outcome, "")

            # Close context to flush the video, then save it to a named file.
            video_path: Optional[str] = None
            try:
                await context.close()
            except Exception:
                pass
            if video is not None:
                named = video_dir / f"{persona.id}.webm"
                try:
                    await video.save_as(str(named))
                    video_path = str(named)
                except Exception:
                    try:
                        video_path = await video.path()
                    except Exception:
                        video_path = None

        outcome = state["outcome"] or PersonaOutcome.ERROR
        duration_s = time.monotonic() - start

        await sink.emit(
            PersonaFinished(
                run_id=run_id,
                persona_id=persona.id,
                outcome=outcome,
                failure_coords=state["failure_coords"],
                failure_reason=state["failure_reason"],
                steps_survived=len(steps),
            )
        )

        return PersonaResult(
            persona_id=persona.id,
            outcome=outcome,
            steps=steps,
            failure_coords=state["failure_coords"],
            failure_step=state["failure_step"],
            failure_reason=state["failure_reason"],
            duration_s=duration_s,
            video_path=video_path,
        )
