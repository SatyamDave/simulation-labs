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

import os

from ghostpanel_contracts import Action, HoloClient, Observation, PersonaConfig

from .perturbation import actuate, perceive, transport_downscale

# Widest frame we SEND to the model (env HAI_IMG_MAX_W). Vision tokens scale with
# pixel area, so capping the transport size cuts per-call inference latency; the
# 0-1000 normalized coords Holo returns are rescaled back to the true viewport.
_DEFAULT_TRANSPORT_MAX_W = 1024


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
        try:
            self._transport_max_w = int(
                os.environ.get("HAI_IMG_MAX_W", _DEFAULT_TRANSPORT_MAX_W)
            )
        except ValueError:
            self._transport_max_w = _DEFAULT_TRANSPORT_MAX_W

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
        # 1. Degrade the screenshot (same dimensions out), then shrink the frame
        #    for transport — fewer vision tokens, faster inference.
        degraded = perceive(obs.raw_png, self.persona)
        send_png, scale = transport_downscale(degraded, self._transport_max_w)

        # 2. Ask Holo for the next action (coords in sent-image pixels).
        # The current URL rides in the task text (navigate() has no page argument)
        # so the model can tell whether its actions are actually going anywhere.
        task = self._effective_task(history)
        if obs.url:
            task = f"{task}\n\nCurrent page URL: {obs.url}"
        raw_action = await self.holo.navigate(send_png, task, history)

        # 3. Map sent-image coords back to the true viewport, then apply tremor
        #    jitter + clamp.
        if scale != 1.0 and raw_action.x is not None and raw_action.y is not None:
            raw_action = raw_action.model_copy(
                update={
                    "x": int(round(raw_action.x / scale)),
                    "y": int(round(raw_action.y / scale)),
                }
            )
        w = obs.viewport.width
        h = obs.viewport.height
        final = actuate(raw_action, self.persona, w, h)
        return final
