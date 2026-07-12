"""Prompt builders for the Holo Models API.

Two prompts, mirroring the hai-cookbook:
  * localization  — ``utils/localization.py``'s exact wording; the model replies
    with ``Click(x, y)`` in the pixel space of the image it was sent.
  * navigation    — ``utils/navigation.py``'s agent loop, flattened to a strict
    single-JSON-object reply so we can parse it without structured-output
    support. The action space is the cookbook's nine actions.

``navigation_prompt`` optionally appends a persona's ``literacy_note`` so the
mechanical "low literacy / non-native" perturbation rides inside the prompt.
"""

from __future__ import annotations

from typing import Optional

from ghostpanel_contracts import PersonaConfig

# Exact cookbook localizer wording (hai-cookbook utils/localization.py).
LOCALIZATION_PROMPT = (
    "Localize an element on the GUI image according to my instructions and "
    "output a click position as Click(x, y) with x num pixels from the left "
    "edge and y num pixels from the top edge."
)

DEFAULT_TASK = "Complete the page's primary goal"

NAVIGATION_SYSTEM_PROMPT = """\
Imagine you are a robot browsing the web, just like humans. Now you need to \
complete a task. In each iteration you receive a screenshot of the current web \
page. Analyse the screenshot, extract any task-relevant information, reason \
briefly, then choose exactly ONE action from the action space below.

Action space (the "action" field must be one of these):
- "click":   click an element.               fields: x, y (integer pixels from the left/top edge of the screenshot), element (short description of what you click)
- "write":   type text at a location, then press Enter. fields: text, x, y, element
- "scroll":  scroll the page.                fields: direction ("up" | "down" | "left" | "right")
- "go_back": go back in browser history.     no extra fields
- "refresh": reload the page.                no extra fields
- "wait":    wait before looking again.      fields: seconds (0-10)
- "goto":    navigate to a URL.              fields: url (must start with http)
- "restart": restart the task from the beginning. no extra fields
- "answer":  the task is complete (or impossible) — give your final answer. fields: text

Reply with a SINGLE JSON object on one line and nothing else — no markdown, no
code fences, no commentary outside the JSON:
{"thought": "<your reasoning, max 4 lines>", "action": "<action name>", <fields for that action>}

Guidelines:
- Accept cookie/consent banners if they block the page.
- Do not scroll more than 3 times in a row.
- Never attempt to log in with credentials you do not have.
- Use search bars by writing into them directly; no need to click them first.
"""


def localization_prompt(instruction: str) -> str:
    """The cookbook localizer prompt plus the caller's instruction."""
    return f"{LOCALIZATION_PROMPT}\nInstruction: {instruction}"


def navigation_prompt(
    task: str,
    history: list[str],
    persona: Optional[PersonaConfig] = None,
) -> str:
    """User-turn text for one navigation step.

    ``history`` is the list of past-action captions (the "TASK: ..." seed entry
    must already have been stripped by the caller — see HoloPersonaAgent).
    When ``persona`` is given and has a ``literacy_note``, it is appended as an
    extra instruction.
    """
    if history:
        past = "\n".join(f"{i + 1}. {caption}" for i, caption in enumerate(history))
    else:
        past = "None yet."
    parts = [f"Task: {task}", f"Previous actions:\n{past}"]
    if persona is not None and persona.literacy_note:
        parts.append(f"Important: {persona.literacy_note}")
    parts.append("What is the next action? Reply with the single JSON object.")
    return "\n\n".join(parts)
