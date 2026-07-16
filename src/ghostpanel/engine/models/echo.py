"""A trivial, deterministic, network-free model backend.

``EchoModelClient`` implements the frozen ``HoloClient`` Protocol (see
``shared/ghostpanel_contracts/contracts.py``) without contacting any vendor. It
returns fixed, scripted actions so the swarm can run fully offline — in CI, in
local smoke tests, or as a fallback when no inference key is configured. Its
existence proves the registry seam accepts a genuinely non-Holo backend.

It is intentionally dumb: it does not look at the screenshot. ``localize``
returns a fixed pixel coordinate and ``navigate`` returns a fixed CLICK Action,
both in TRUE viewport pixel space (no denormalization), exactly like
``FakeHoloClient`` — so the runner executes the coords verbatim.
"""

from __future__ import annotations

from ghostpanel_contracts import Action, ActionType


class EchoModelClient:
    """A deterministic ``HoloClient`` that echoes fixed scripted actions.

    Matches ``LiveHoloClient``/``FakeHoloClient``'s public async surface exactly:
    ``async def localize(image_png, instruction) -> tuple[int, int]`` and
    ``async def navigate(image_png, task, history) -> Action``. Satisfies the
    ``@runtime_checkable`` ``HoloClient`` Protocol
    (``isinstance(EchoModelClient(), HoloClient)`` is True).
    """

    def __init__(self, x: int = 100, y: int = 100) -> None:
        self._x = int(x)
        self._y = int(y)

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        """Return a fixed (x, y) in the pixel space of the image passed in."""
        return self._x, self._y

    async def navigate(
        self, image_png: bytes, task: str, history: list[str]
    ) -> Action:
        """Return a deterministic CLICK Action (true viewport pixels)."""
        return Action(
            type=ActionType.CLICK,
            x=self._x,
            y=self._y,
            caption=f"Clicking at ({self._x}, {self._y})",
            raw="echo:fixed-click",
        )
