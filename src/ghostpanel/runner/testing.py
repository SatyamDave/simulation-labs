"""Test doubles owned by Agent 2.

``CollectingEventSink`` is in the shared class registry (Agent 3's tests use it
too). ``StubPersonaAgent`` keeps runner tests fully decoupled from the engine:
it replays scripted contract Actions with no network, no Holo, no API keys.
"""

from __future__ import annotations

from pydantic import BaseModel

from ghostpanel_contracts import Action, ActionType, Observation, PersonaConfig


class CollectingEventSink:
    """EventSink that appends every emitted event to ``self.events``."""

    def __init__(self) -> None:
        self.events: list[BaseModel] = []

    async def emit(self, event: BaseModel) -> None:
        self.events.append(event)


class StubPersonaAgent:
    """PersonaAgent that replays a fixed script of contract Actions.

    Cycles through the script when it runs out (so a short script can exhaust
    a step budget). Records every ``history`` it was handed in
    ``self.seen_histories`` so tests can assert the "TASK: ..." seeding
    convention; the stub itself ignores the seed.
    """

    def __init__(self, persona: PersonaConfig, script: list[Action]) -> None:
        self.persona = persona
        self._script = list(script)
        self._calls = 0
        self.seen_histories: list[list[str]] = []

    async def decide(self, obs: Observation, history: list[str]) -> Action:
        self.seen_histories.append(list(history))
        if not self._script:
            return Action(type=ActionType.ANSWER, caption="done (empty script)")
        action = self._script[self._calls % len(self._script)]
        self._calls += 1
        return action
