"""Test doubles owned by Agent 2, usable by Agent 3's tests too.

- `CollectingEventSink` — an `EventSink` (registry name) that stores every emitted
  event in `.events`.
- `StubPersonaAgent` — a `PersonaAgent` that returns a scripted list of `Action`s,
  so the session runner can be tested with no engine and no network.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from pydantic import BaseModel

from ghostpanel_contracts import Action, ActionType, Observation, PersonaConfig


class CollectingEventSink:
    """An EventSink that just accumulates events (for tests / debugging)."""

    def __init__(self) -> None:
        self.events: list[BaseModel] = []

    async def emit(self, event: BaseModel) -> None:
        self.events.append(event)

    # --- convenience helpers for assertions ---------------------------------
    def of_type(self, model_cls: type) -> list[BaseModel]:
        return [e for e in self.events if isinstance(e, model_cls)]


class StubPersonaAgent:
    """A PersonaAgent that replays a fixed script of Actions.

    `script` is any iterable of `Action`. Each `decide()` returns the next one; once
    the script is exhausted it returns an ANSWER action (persona declares done), so a
    short script never wedges the loop. `decide_delay_s` sleeps inside decide() to
    simulate model latency / rate-limiter queueing (which must NOT count against the
    persona's deadline).
    """

    def __init__(
        self,
        persona: PersonaConfig,
        script: Iterable[Action],
        decide_delay_s: float = 0.0,
    ) -> None:
        self.persona = persona
        self._script: list[Action] = list(script)
        self._i = 0
        self._delay = decide_delay_s

    async def decide(self, obs: Observation, history: list[str]) -> Action:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if self._i < len(self._script):
            action = self._script[self._i]
            self._i += 1
            return action
        return Action(type=ActionType.ANSWER, caption="done", text="done")
