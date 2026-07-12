"""HoloPersonaAgent — one persona's decision loop.

decide() = perceive (degrade the screenshot) -> holo.navigate -> actuate (jitter
the click). The returned Action is in TRUE viewport pixels; the runner executes
it verbatim.

Task string: the HoloClient.navigate contract is ``(image_png, task, history)``
with no persona argument, so this agent owns the persona-specific prompt shaping.
The task is stored on the agent (constructor ``task`` kwarg, default ""). The
agent prepends the persona's ``literacy_note`` / language hint to the task text so
it reaches the live model even through the persona-free navigate() signature.
"""

from __future__ import annotations

from typing import Optional

from ghostpanel_contracts import Action, HoloClient, Observation, PersonaConfig

from .perturbation import actuate, perceive


class HoloPersonaAgent:
    """Concrete PersonaAgent. Registry signature: ``(persona, holo)``.

    An optional ``task`` kwarg lets the composition root bind the run goal to the
    agent (recommended). If ``task`` is empty, decide() falls back to any task text
    carried on the history convention (first history entry prefixed "task:").
    """

    def __init__(
        self,
        persona: PersonaConfig,
        holo: HoloClient,
        task: str = "",
    ) -> None:
        self.persona = persona
        self.holo = holo
        self.task = task or ""

    def _effective_task(self, history: list[str]) -> str:
        task = self.task
        if not task and history:
            first = history[0]
            if first.lower().startswith("task:"):
                task = first.split(":", 1)[1].strip()
        # Fold persona cognition/literacy into the task text so it survives the
        # persona-free HoloClient.navigate() signature.
        extras: list[str] = []
        note = (self.persona.literacy_note or "").strip()
        if note:
            extras.append(note)
        if self.persona.language and self.persona.language != "en":
            extras.append(
                f"You read more comfortably in '{self.persona.language}' than English."
            )
        if extras:
            return task + "\n\n" + "\n".join(extras)
        return task

    async def decide(self, obs: Observation, history: list[str]) -> Action:
        # 1. Degrade the screenshot (same dimensions out).
        degraded = perceive(obs.raw_png, self.persona)

        # 2. Ask Holo for the next action (coords in image/viewport pixels).
        task = self._effective_task(history)
        raw_action = await self.holo.navigate(degraded, task, history)

        # 3. Apply tremor jitter + clamp to the true viewport.
        w = obs.viewport.width
        h = obs.viewport.height
        final = actuate(raw_action, self.persona, w, h)
        return final
