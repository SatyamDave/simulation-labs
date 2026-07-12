"""HoloPersonaAgent (Agent 1): one persona's decision loop step.

decide(obs, history) = perceive -> holo.navigate -> actuate, returning an
Action in TRUE viewport pixels (the runner executes it verbatim).

History convention (FROZEN, all five agents follow it)
------------------------------------------------------
The runner seeds the ``history`` list it passes to :meth:`decide` with the
task as element 0, formatted exactly ``"TASK: <task text>"``. This agent
extracts the task from that leading entry and does NOT treat it as a past
action when building the prompt history. If the entry is absent, the task
falls back to ``"Complete the page's primary goal"``.

Literacy note: the ``HoloClient.navigate`` Protocol takes only (image, task,
history), so the persona's ``literacy_note`` is folded into the task text
here before the client is called.
"""

from __future__ import annotations

from ghostpanel_contracts import Action, HoloClient, Observation, PersonaConfig

from .perturbation import actuate, perceive
from .prompts import DEFAULT_TASK

TASK_PREFIX = "TASK: "


class HoloPersonaAgent:
    """Decides the next Action for one persona: perturb(image) -> Holo -> jitter."""

    def __init__(self, persona: PersonaConfig, holo: HoloClient) -> None:
        self.persona = persona
        self.holo = holo

    async def decide(self, obs: Observation, history: list[str]) -> Action:
        task = DEFAULT_TASK
        past = list(history or [])
        if past and past[0].startswith(TASK_PREFIX):
            task = past[0][len(TASK_PREFIX):].strip() or DEFAULT_TASK
            past = past[1:]
        if self.persona.literacy_note:
            task = f"{task}\n\nImportant: {self.persona.literacy_note}"

        degraded_png = perceive(obs.raw_png, self.persona)
        action = await self.holo.navigate(degraded_png, task, past)
        return actuate(action, self.persona, obs.viewport.width, obs.viewport.height)
