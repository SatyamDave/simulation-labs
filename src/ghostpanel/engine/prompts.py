"""Prompt builders for the Holo Models API.

Two builders:
  * ``localization_prompt`` — the exact cookbook localizer wording; the model
    replies with ``Click(x, y)``.
  * ``navigation_prompt`` — describes the action space, folds in the task and the
    history of prior action captions, and appends the persona's ``literacy_note``
    (the LOW_LITERACY prompt modifier) when set.
"""

from __future__ import annotations

from ghostpanel_contracts import PersonaConfig

# The verbatim localizer instruction from the hai-cookbook (utils/localization.py).
_LOCALIZER = (
    "Localize an element on the GUI image according to my instructions and "
    "output a click position as Click(x, y) with x num pixels from the left "
    "edge and y num pixels from the top edge."
)


def localization_prompt(instruction: str) -> str:
    """Return the localizer prompt for a single element instruction."""
    instruction = (instruction or "").strip()
    return f"{_LOCALIZER}\n\nInstruction: {instruction}"


# Human-facing description of the Holo navigation action space. The model is
# asked to return a single action. We parse either the `Click(x, y)` short form
# or a JSON object (see holo_client._parse_navigation).
_ACTION_SPACE = """\
You control a web browser to accomplish a task. Look at the screenshot and choose
exactly ONE next action from this action space:

- click(x, y)                — click at pixel (x, y) from the top-left of the image
- write(x, y, text)          — click the field at (x, y) and type `text` (Enter is pressed)
- scroll(direction)          — scroll the page: up | down | left | right
- go_back()                  — navigate to the previous page
- refresh()                  — reload the current page
- wait(seconds)              — wait 0-10 seconds for the page to settle
- goto(url)                  — navigate directly to a URL
- restart()                  — start the task over from the beginning
- answer(text)               — the task is complete; `text` is the final answer

Coordinates are in pixels measured from the top-left corner of the image you were
given. Respond with a single action. Prefer a JSON object with EVERY key named,
including "y", e.g.:
  {"action": "click", "x": 512, "y": 240, "label": "Accept cookies button"}
  {"action": "write", "x": 300, "y": 120, "text": "hello", "label": "Email field"}
  {"action": "scroll", "direction": "down"}
  {"action": "answer", "text": "done"}
"label" is a short name for the element you are acting on. You may add a short
"reason" field. Do not output anything except the JSON object.

Guidelines:
- If a cookie banner, consent prompt, or modal dialog covers the page, DISMISS it
  first (e.g. click its accept/close button) before doing anything else.
- Make real progress toward the task each step: fill required fields, then submit.
- If your previous action did not change the screen, DO NOT repeat it — try a
  different element, scroll to reveal more, or a different approach.
- To finish a signup/checkout you usually must click the button that performs the
  action (e.g. "Create account", "Sign up"), not a promotional or secondary button.
- Only use answer() when the task is genuinely complete (e.g. a success/confirmation
  message is visible)."""


def navigation_prompt(task: str, history: list[str], persona: PersonaConfig) -> str:
    """Build the navigation prompt.

    Args:
        task: the user goal, e.g. "Sign up for an account".
        history: captions of prior actions, most recent last.
        persona: used for its ``literacy_note`` (LOW_LITERACY modifier) and language.
    """
    task = (task or "").strip()
    parts: list[str] = [_ACTION_SPACE, "", f"Task: {task}"]

    if history:
        recent = history[-10:]
        lines = "\n".join(f"  {i + 1}. {h}" for i, h in enumerate(recent))
        parts.append("")
        parts.append("Actions you have already taken (oldest first):")
        parts.append(lines)
    else:
        parts.append("")
        parts.append("You have not taken any actions yet.")

    note = (persona.literacy_note or "").strip()
    if note:
        parts.append("")
        parts.append(note)

    if persona.language and persona.language != "en":
        parts.append("")
        parts.append(
            f"Note: you are more comfortable in '{persona.language}' than in English."
        )

    return "\n".join(parts)
