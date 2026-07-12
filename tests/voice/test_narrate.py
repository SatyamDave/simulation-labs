"""Tests for the exit-interview template fallback (no API key, no network)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ghostpanel_contracts import PersonaConfig, PersonaResult

from ghostpanel.voice.narrate import (
    template_exit_interview,
    write_exit_interview,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "run.json"


def _grandma_result() -> PersonaResult:
    data = json.loads(FIXTURE.read_text())
    raw = next(r for r in data["results"] if r["persona_id"] == "grandma-72")
    return PersonaResult.model_validate(raw)


def _grandma_persona() -> PersonaConfig:
    return PersonaConfig(id="grandma-72", name="Margaret, 72", language="en")


def test_template_references_actual_trace():
    result = _grandma_result()
    text = template_exit_interview(result, _grandma_persona())
    low = text.lower()
    # grounded in the real trace: the decoy 'Explore plans' button
    assert "decoy" in low
    assert "explore plans" in low
    # first person
    assert "i " in low or low.startswith("i")
    assert len(text) > 0


def test_write_exit_interview_no_key_uses_template(monkeypatch):
    # Isolate from an ambient ANTHROPIC_USE_CLAUDE_CLI (set in .env) — this test
    # asserts the pure no-key/no-CLI path; the CLI branch has its own tests.
    monkeypatch.delenv("ANTHROPIC_USE_CLAUDE_CLI", raising=False)
    result = _grandma_result()
    text = asyncio.run(
        write_exit_interview(result, _grandma_persona(), anthropic_key=None)
    )
    # identical to the deterministic template when no key is present
    assert text == template_exit_interview(result, _grandma_persona())
    assert "decoy" in text.lower()


def test_template_success_case():
    result = PersonaResult.model_validate(
        {
            "persona_id": "power-user",
            "outcome": "success",
            "steps": [
                {
                    "persona_id": "power-user",
                    "step": 0,
                    "action": {"type": "click", "caption": "Click Sign up"},
                }
            ],
        }
    )
    text = template_exit_interview(result, PersonaConfig(id="power-user", name="Alex"))
    assert "sign up" in text.lower()
