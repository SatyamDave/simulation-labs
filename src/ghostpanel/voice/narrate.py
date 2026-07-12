"""Action-trace -> first-person exit-interview TEXT.

Given the REAL trace (persona description, the ordered step captions, the
outcome and failure_reason), produce 1-3 first-person sentences in the
persona's voice and language. Uses Claude when an Anthropic key is supplied;
otherwise (or on any API failure) falls back to a deterministic template that
still quotes the actual captions/outcome — the demo never hard-fails on a
missing key.
"""

from __future__ import annotations

import os
from typing import Optional

from ghostpanel_contracts import PersonaConfig, PersonaOutcome, PersonaResult

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = (
    "You are a synthetic usability-test participant giving a spoken exit interview. "
    "You will be given who you are, exactly what you did on the website (an ordered "
    "action trace), and how your session ended. Reply with 1-3 short first-person "
    "sentences, in character, explaining what happened and why you finished or gave "
    "up. Ground every claim in the trace — mention the actual things you clicked or "
    "typed; never invent steps. No preamble, no quotes, just the sentences. "
    "Reply in the language with ISO code '{language}'."
)


def _captions(result: PersonaResult) -> list[str]:
    return [s.action.caption for s in result.steps if s.action.caption]


def _trace_block(result: PersonaResult, persona: PersonaConfig) -> str:
    lines = [
        f"Persona: {persona.name} — {persona.blurb or persona.id}",
        f"Outcome: {result.outcome.value}",
    ]
    if result.failure_reason:
        lines.append(f"Failure reason: {result.failure_reason}")
    if result.duration_s:
        lines.append(f"Session length: {result.duration_s:.0f}s over {len(result.steps)} steps")
    lines.append("Actions, in order:")
    caps = _captions(result)
    if caps:
        lines += [f"  {i + 1}. {c}" for i, c in enumerate(caps)]
    else:
        lines.append("  (no recorded actions)")
    return "\n".join(lines)


def template_exit_interview(result: PersonaResult, persona: PersonaConfig) -> str:
    """Deterministic, key-free fallback. Still grounded: quotes the real
    captions and reflects the real outcome/failure_reason."""
    caps = _captions(result)
    first = caps[0] if caps else None
    last = caps[-1] if caps else None

    if result.outcome == PersonaOutcome.SUCCESS:
        if first and last and first != last:
            return (
                f"I got it done. I started with '{first}' and after "
                f"{len(caps)} steps '{last}' finished the job."
            )
        if last:
            return f"I got it done — '{last}' did the trick."
        return "I got it done without any trouble."

    reason = f" {result.failure_reason}" if result.failure_reason else ""
    if result.outcome == PersonaOutcome.STUCK:
        tail = f"The last thing I tried was '{last}' and nothing changed." if last else ""
        return f"I gave up — I just couldn't get anywhere. {tail}{reason}".strip()
    if result.outcome == PersonaOutcome.STEP_BUDGET:
        tail = f"I even tried '{last}' near the end." if last else ""
        return (
            f"I tried {len(caps) or 'many'} different things and ran out of patience "
            f"before it worked. {tail}{reason}".strip()
        )
    if result.outcome == PersonaOutcome.TIME_BUDGET:
        tail = f"I only got as far as '{last}'." if last else ""
        return f"It was taking far too long, so I left. {tail}{reason}".strip()
    # ERROR — infra failure, keep it neutral.
    return f"Something broke before I could finish; it wasn't anything I did.{reason}".strip()


async def write_exit_interview(
    result: PersonaResult,
    persona: PersonaConfig,
    anthropic_key: Optional[str] = None,
) -> str:
    """Return 1-3 first-person sentences explaining this persona's session.

    With `anthropic_key`: asks Claude (model from ANTHROPIC_MODEL env) in the
    persona's language. Without a key — or if the API call fails — returns the
    deterministic grounded template instead.
    """
    if not anthropic_key:
        return template_exit_interview(result, persona)

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=anthropic_key)
        response = await client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            max_tokens=300,
            system=_SYSTEM_PROMPT.format(language=persona.language),
            messages=[{"role": "user", "content": _trace_block(result, persona)}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        return text or template_exit_interview(result, persona)
    except Exception:
        # Demo-first: a flaky/exhausted API must never kill the run.
        return template_exit_interview(result, persona)
