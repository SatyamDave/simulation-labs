"""Tests for GradiumVoiceEngine — protocol conformance + no-key behavior.

Unit tests must NOT need an API key and must NOT hit the network. A live smoke
test is gated behind GRADIUM_API_KEY.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from ghostpanel_contracts import (
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    VoiceEngine,
)

from ghostpanel.voice.gradium_voice import GradiumVoiceEngine


def test_construction_with_no_key_does_not_crash(tmp_path):
    engine = GradiumVoiceEngine(api_key=None, artifact_dir=tmp_path)
    assert engine is not None


def test_satisfies_voice_engine_protocol(tmp_path):
    engine = GradiumVoiceEngine(api_key=None, artifact_dir=tmp_path)
    assert isinstance(engine, VoiceEngine)


def test_exit_interview_no_key_raises_clear_error(tmp_path):
    engine = GradiumVoiceEngine(api_key=None, artifact_dir=tmp_path)
    result = PersonaResult(persona_id="p", outcome=PersonaOutcome.STUCK)
    persona = PersonaConfig(id="p", name="P")
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(engine.exit_interview(result, persona))
    assert "api key" in str(exc.value).lower()
    # no partial mutation on the no-key path
    assert result.audio_path is None


def test_mutter_no_key_raises_clear_error(tmp_path):
    engine = GradiumVoiceEngine(api_key=None, artifact_dir=tmp_path)
    with pytest.raises(RuntimeError):
        asyncio.run(engine.mutter("hello", voice_id=None))


@pytest.mark.skipif(
    not os.environ.get("GRADIUM_API_KEY"),
    reason="live smoke needs GRADIUM_API_KEY",
)
def test_live_exit_interview_produces_wav(tmp_path):
    engine = GradiumVoiceEngine(
        api_key=os.environ["GRADIUM_API_KEY"],
        artifact_dir=tmp_path,
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    result = PersonaResult(
        persona_id="grandma-72",
        outcome=PersonaOutcome.STUCK,
        failure_reason="Clicked the blue 'Explore plans' decoy repeatedly.",
    )
    persona = PersonaConfig(id="grandma-72", name="Margaret, 72")
    path = asyncio.run(engine.exit_interview(result, persona))
    from pathlib import Path

    assert Path(path).exists()
    assert Path(path).stat().st_size > 0
    assert result.transcript
    assert result.audio_path == path
