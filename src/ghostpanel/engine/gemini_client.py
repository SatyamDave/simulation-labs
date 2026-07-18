"""Gemini backend for the persona swarm (``MODEL_BACKEND=gemini``).

``GeminiClient`` drives the SAME swarm through Google's OpenAI-compatible
endpoint (``https://generativelanguage.googleapis.com/v1beta/openai/``). Built
for the Stanford x DeepMind hackathon, where every submission must use Gemini;
kept as a permanent backend because the seam costs nothing.

Coordinate contract: Gemini's UI grounding is trained on a 0-1000 normalized
grid — the same convention the hosted Holo3.1 API uses — so the existing
``normalize=True`` denormalization path in ``parse_action`` applies unchanged.
One critical difference: Holo emits 0-1000 coords regardless of prompt wording
(its cookbook localizer says "pixels" and the model still returns grid coords,
verified live), while Gemini follows coordinate instructions literally. The
prompts here therefore say 0-1000 EXPLICITLY — never reuse the Holo wording
for Gemini, or a compliant pixel-space answer would be denormalized twice.
"""

from __future__ import annotations

from . import prompts
from .holo_client import LiveHoloClient, _navigate_prompt

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
# Free-tier Flash allows ~10 RPM; raise GEMINI_RPM in .env on a paid tier.
DEFAULT_GEMINI_RPM = 10.0

# Exact Holo wordings we rewrite -> grid wordings. If the source prompt drifts
# and a wording disappears, we raise instead of silently sending Gemini a
# pixel-space instruction (the failure would otherwise be subtle: every click
# lands in the top-left ~2% of the page after double scaling).
_LOC_REWRITE = (
    "output a click position as Click(x, y) with x num pixels from the left "
    "edge and y num pixels from the top edge.",
    "output a click position as Click(x, y) where x and y are integers on a "
    "0-1000 normalized grid: x measured from the left edge (1000 = right "
    "edge) and y measured from the top edge (1000 = bottom edge).",
)
_NAV_REWRITES = (
    (
        "- click(x, y)                — click at pixel (x, y) from the top-left of the image",
        "- click(x, y)                — click at grid point (x, y); coordinates are on a 0-1000 normalized grid",
    ),
    (
        "Coordinates are in pixels measured from the top-left corner of the image you were\n"
        "given.",
        "Coordinates are integers on a 0-1000 normalized grid measured from the top-left\n"
        "corner of the image: x=1000 is the right edge, y=1000 is the bottom edge. Never\n"
        "answer in raw pixels.",
    ),
)


def _rewrite(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(
            "Holo prompt wording drifted; update the Gemini rewrites in "
            "gemini_client.py (missing fragment: %r)" % old[:60]
        )
    return text.replace(old, new)


def gemini_localization_prompt(instruction: str) -> str:
    """The Holo localizer prompt, rewritten to demand 0-1000 grid coords."""
    return _rewrite(prompts.localization_prompt(instruction), *_LOC_REWRITE)


def gemini_navigation_prompt(task: str, history: list[str]) -> str:
    """The persona-free navigation prompt, rewritten to the 0-1000 grid."""
    text = _navigate_prompt(task, history)
    for old, new in _NAV_REWRITES:
        text = _rewrite(text, old, new)
    return text


class GeminiClient(LiveHoloClient):
    """LiveHoloClient pointed at Gemini, with grid-explicit prompts.

    Everything else — transport, retries, rate limiting, parsing, 0-1000
    denormalization — is inherited unchanged.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
        model: str = DEFAULT_GEMINI_MODEL,
        rpm: float = DEFAULT_GEMINI_RPM,
        limiter=None,
        max_retries: int = 4,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            rpm=rpm,
            limiter=limiter,
            max_retries=max_retries,
        )

    def _localize_prompt(self, instruction: str) -> str:
        return gemini_localization_prompt(instruction)

    def _navigation_prompt(self, task: str, history: list[str]) -> str:
        return gemini_navigation_prompt(task, history)
