"""Claude-CLI narration path: opt-in via ANTHROPIC_USE_CLAUDE_CLI, always
falls back to the deterministic template on any failure."""

import pytest

from ghostpanel.voice import narrate
from ghostpanel.voice.narrate import template_exit_interview, write_exit_interview
from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    StepRecord,
)


def _result() -> PersonaResult:
    return PersonaResult(
        persona_id="grandma-72",
        outcome=PersonaOutcome.STUCK,
        failure_reason="repeated action: clicking Explore plans",
        steps=[
            StepRecord(
                persona_id="grandma-72",
                step=0,
                action=Action(type=ActionType.CLICK, x=1, y=2, caption="clicking Explore plans"),
            )
        ],
    )


def _persona() -> PersonaConfig:
    return PersonaConfig(id="grandma-72", name="Margaret, 72")


async def test_cli_disabled_by_default_uses_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_USE_CLAUDE_CLI", raising=False)

    async def _boom(*a, **k):  # the CLI must not even be attempted
        raise AssertionError("CLI attempted while disabled")

    monkeypatch.setattr(narrate, "_claude_cli_exit_interview", _boom)
    text = await write_exit_interview(_result(), _persona(), anthropic_key=None)
    assert text == template_exit_interview(_result(), _persona())


async def test_cli_enabled_uses_cli_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_USE_CLAUDE_CLI", "1")

    async def _fake(result, persona, timeout_s=90.0):
        return "I kept pressing the big blue button and nothing happened."

    monkeypatch.setattr(narrate, "_claude_cli_exit_interview", _fake)
    text = await write_exit_interview(_result(), _persona(), anthropic_key=None)
    assert text == "I kept pressing the big blue button and nothing happened."


async def test_cli_failure_falls_back_to_template(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_USE_CLAUDE_CLI", "true")

    async def _fail(result, persona, timeout_s=90.0):
        return None

    monkeypatch.setattr(narrate, "_claude_cli_exit_interview", _fail)
    text = await write_exit_interview(_result(), _persona(), anthropic_key=None)
    assert text == template_exit_interview(_result(), _persona())


async def test_cli_missing_binary_returns_none(monkeypatch):
    monkeypatch.setattr(narrate.shutil, "which", lambda _: None)
    assert await narrate._claude_cli_exit_interview(_result(), _persona()) is None


@pytest.mark.anyio
async def test_explicit_key_still_prefers_sdk(monkeypatch):
    # With a key present the CLI must not be consulted even when enabled.
    monkeypatch.setenv("ANTHROPIC_USE_CLAUDE_CLI", "1")

    async def _boom(*a, **k):
        raise AssertionError("CLI attempted despite explicit key")

    monkeypatch.setattr(narrate, "_claude_cli_exit_interview", _boom)
    # Bogus key -> SDK path raises internally -> template fallback (never CLI).
    text = await write_exit_interview(_result(), _persona(), anthropic_key="sk-bogus")
    assert text == template_exit_interview(_result(), _persona())
