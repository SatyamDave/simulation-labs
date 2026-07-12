"""Turn a persona's real action trace into a first-person exit-interview line.

`write_exit_interview` is the single entry point. WITH an Anthropic key it asks
Claude (Anthropic SDK) for 1-3 first-person sentences grounded in the ordered
step captions + outcome + failure_reason, in the persona's language. WITHOUT a
key, if ``ANTHROPIC_USE_CLAUDE_CLI`` is truthy it asks the locally-authenticated
Claude Code CLI (``claude -p`` — subscription login, no API key needed) instead.
Every path falls back to a deterministic template that still references the
actual captions/outcome, so tests and the demo never hard-fail.
"""

from __future__ import annotations

import asyncio
import os
import shutil

from ghostpanel_contracts import (
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
)

# Default model if ANTHROPIC_MODEL is unset. Only used on the live path.
_DEFAULT_MODEL = "claude-sonnet-5"

_OUTCOME_PHRASE = {
    PersonaOutcome.SUCCESS: "I finally got it done",
    PersonaOutcome.STEP_BUDGET: "I ran out of patience clicking around",
    PersonaOutcome.TIME_BUDGET: "I ran out of time",
    PersonaOutcome.STUCK: "I got stuck and gave up",
    PersonaOutcome.ERROR: "something broke and I couldn't continue",
}


def _captions(result: PersonaResult) -> list[str]:
    """Ordered human-readable captions of what the persona actually did."""
    caps = []
    for step in result.steps:
        cap = (step.action.caption or step.action.raw or "").strip()
        if cap:
            caps.append(cap)
    return caps


def template_exit_interview(
    result: PersonaResult, persona: PersonaConfig
) -> str:
    """Deterministic fallback grounded in the real trace (no API needed)."""
    captions = _captions(result)
    outcome_phrase = _OUTCOME_PHRASE.get(
        result.outcome, "I stopped trying"
    )

    if captions:
        # Compress consecutive repeats ("clicking X, then clicking X, ..." →
        # "clicking X again and again") — that's how a person tells it. Captions
        # are gerund phrases, so "I tried clicking…" reads naturally.
        compressed: list[str] = []
        repeats = 1
        for caption, nxt in zip(captions, captions[1:] + [None]):
            if caption == nxt:
                repeats += 1
                continue
            phrase = caption.lower()
            if repeats > 1:
                phrase += " again and again" if repeats > 2 else " twice"
            compressed.append(phrase)
            repeats = 1
        if len(compressed) == 1:
            steps_sentence = f"I tried {compressed[0]}"
        else:
            body = ", then ".join(compressed[:-1])
            steps_sentence = f"First I tried {body}, then {compressed[-1]}"
    else:
        steps_sentence = "I looked around the page"

    parts = [steps_sentence + "."]
    if result.failure_reason:
        parts.append(f"In the end, {result.failure_reason.rstrip('.')}.")
    if result.outcome == PersonaOutcome.SUCCESS:
        parts.append(f"{outcome_phrase.capitalize()}.")
    else:
        parts.append(f"{outcome_phrase.capitalize()}.")
    return " ".join(parts)


def _build_prompt(result: PersonaResult, persona: PersonaConfig) -> str:
    captions = _captions(result)
    steps_block = (
        "\n".join(f"{i + 1}. {c}" for i, c in enumerate(captions))
        or "(no recorded steps)"
    )
    return (
        f"You are role-playing a real user who just tried to use a website.\n"
        f"Persona: {persona.name}. {persona.blurb}\n"
        f"What you actually did, in order:\n{steps_block}\n"
        f"How it ended: {result.outcome.value}.\n"
        f"Recorded reason: {result.failure_reason or '(none)'}\n\n"
        f"Speak as this persona in FIRST PERSON. Give 1-3 short sentences "
        f"explaining, in plain human terms, what you were trying to do and why "
        f"you {'succeeded' if result.outcome == PersonaOutcome.SUCCESS else 'gave up'}. "
        f"Ground every claim in the steps above; do not invent UI you never touched. "
        f"Answer in language code '{persona.language}'. Output ONLY the sentences."
    )


def _cli_narration_enabled() -> bool:
    return os.environ.get("ANTHROPIC_USE_CLAUDE_CLI", "").lower() in ("1", "true", "yes")


async def _claude_cli_exit_interview(
    result: PersonaResult, persona: PersonaConfig, timeout_s: float = 90.0
) -> str | None:
    """Ask the locally-authenticated Claude Code CLI (subscription login, no API
    key) for the narration. Returns None on any failure so callers fall back."""
    binary = shutil.which("claude")
    if binary is None:
        return None
    model = os.environ.get("ANTHROPIC_MODEL") or _DEFAULT_MODEL
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, "-p", _build_prompt(result, persona),
            "--model", model, "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except (asyncio.TimeoutError, OSError):
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 - already gone
            pass
        return None
    if proc.returncode != 0:
        return None
    text = stdout.decode("utf-8", errors="replace").strip()
    return text or None


async def write_exit_interview(
    result: PersonaResult,
    persona: PersonaConfig,
    anthropic_key: str | None = None,
) -> str:
    """Return a short first-person exit-interview line for this persona.

    Uses Claude via the Anthropic SDK when ``anthropic_key`` is provided; with
    no key and ``ANTHROPIC_USE_CLAUDE_CLI`` enabled, uses the Claude Code CLI's
    subscription login. Every path falls back to the deterministic template.
    """
    if not anthropic_key:
        if _cli_narration_enabled():
            text = await _claude_cli_exit_interview(result, persona)
            if text:
                return text
        return template_exit_interview(result, persona)

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=anthropic_key)
        model = os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        resp = await client.messages.create(
            model=model,
            max_tokens=200,
            messages=[
                {"role": "user", "content": _build_prompt(result, persona)}
            ],
        )
        text = "".join(
            block.text
            for block in resp.content
            if getattr(block, "type", None) == "text"
        ).strip()
        return text or template_exit_interview(result, persona)
    except Exception:
        # Never hard-fail the demo on an API hiccup — fall back to the template.
        return template_exit_interview(result, persona)
