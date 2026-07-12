"""GradiumVoiceEngine: protocol conformance, keyless behavior (clear error,
no network), synthesis via an injected fake client, and voice assignment.
A live smoke test runs only when GRADIUM_API_KEY is set."""

import os
import wave
from types import SimpleNamespace

import pytest

from ghostpanel_contracts import PersonaConfig, VoiceEngine

from ghostpanel.voice.gradium_voice import GradiumVoiceEngine
from ghostpanel.voice.voices import assign_voices, pick_voice

FAKE_WAV = b"RIFF....WAVEfmt fake-bytes"


class FakeGradiumClient:
    """Stands in for gradium.GradiumClient — records calls, never networks."""

    def __init__(self):
        self.tts_calls = []

    async def tts(self, setup, text):
        self.tts_calls.append((dict(setup), text))
        return SimpleNamespace(raw_data=FAKE_WAV, sample_rate=24000)

    async def voice_get(self, include_catalog=False):
        return {
            "catalog": [
                {"uid": "v-old", "name": "Edith", "description": "Warm elderly grandmother"},
                {"uid": "v-fast", "name": "Zip", "description": "Fast energetic young voice"},
                {"uid": "v-flat", "name": "Unit", "description": "Neutral synthetic narrator"},
            ]
        }


@pytest.fixture()
def engine(tmp_path, monkeypatch) -> GradiumVoiceEngine:
    monkeypatch.delenv("GRADIUM_API_KEY", raising=False)
    return GradiumVoiceEngine(api_key=None, artifact_dir=tmp_path)


def test_satisfies_voice_engine_protocol(engine):
    assert isinstance(engine, VoiceEngine)


def test_construction_without_key_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.delenv("GRADIUM_API_KEY", raising=False)
    GradiumVoiceEngine(None, tmp_path)  # must not raise at wire-up time


async def test_synthesis_without_key_raises_clear_error(
    engine, grandma_result, grandma_persona
):
    with pytest.raises(RuntimeError, match="GRADIUM_API_KEY"):
        await engine.exit_interview(grandma_result, grandma_persona)
    with pytest.raises(RuntimeError, match="GRADIUM_API_KEY"):
        await engine.mutter("hmm, where is the sign-up?", voice_id=None)


async def test_exit_interview_writes_wav_and_fills_result(
    engine, tmp_path, grandma_result, grandma_persona
):
    engine._client = FakeGradiumClient()
    engine.run_id = "demo-run-0001"
    path = await engine.exit_interview(grandma_result, grandma_persona)

    assert path == str(tmp_path / "demo-run-0001" / "grandma-72.wav")
    assert (tmp_path / "demo-run-0001" / "grandma-72.wav").read_bytes() == FAKE_WAV
    assert grandma_result.audio_path == path
    # transcript is the narrated text, grounded in the trace
    assert "Explore plans" in grandma_result.transcript
    # the synthesized text is the transcript
    (_, spoken), = engine._client.tts_calls
    assert spoken == grandma_result.transcript


async def test_exit_interview_defaults_run_dir_and_respects_voice_id(
    engine, tmp_path, grandma_result, grandma_persona
):
    engine._client = FakeGradiumClient()
    persona = grandma_persona.model_copy(update={"voice_id": "v-old"})
    path = await engine.exit_interview(grandma_result, persona)
    assert path == str(tmp_path / "default" / "grandma-72.wav")
    (setup, _), = engine._client.tts_calls
    assert setup["voice_id"] == "v-old"
    assert setup["output_format"] == "wav"


async def test_mutter_writes_clip(engine, tmp_path):
    engine._client = FakeGradiumClient()
    path = await engine.mutter("where on earth is the button", voice_id="v-old")
    assert path.endswith(".wav") and os.path.exists(path)
    (setup, text), = engine._client.tts_calls
    assert setup["voice_id"] == "v-old"
    assert text == "where on earth is the button"


# --- voice assignment ------------------------------------------------------
async def test_assign_voices_distinct_and_fitting(grandma_persona):
    personas = [
        grandma_persona,  # should get the elderly-sounding voice
        PersonaConfig(id="impatient-mobile", name="Priya", blurb="Impatient, always in a hurry"),
        PersonaConfig(id="ai-agent", name="Agent", blurb="Headless AI agent"),
    ]
    assignment = await assign_voices(personas, FakeGradiumClient())
    assert assignment["grandma-72"] == "v-old"
    assert assignment["impatient-mobile"] == "v-fast"
    assert assignment["ai-agent"] == "v-flat"
    assert len(set(assignment.values())) == 3  # distinct


def test_pick_voice_respects_pinned_voice_id(grandma_persona):
    pinned = grandma_persona.model_copy(update={"voice_id": "my-clone"})
    assert pick_voice(pinned, [{"uid": "v-old", "name": "Edith"}], set()) == "my-clone"


def test_pick_voice_reuses_when_catalog_exhausted(grandma_persona):
    available = [{"uid": "v-old", "name": "Edith", "description": "elderly"}]
    assert pick_voice(grandma_persona, available, used={"v-old"}) == "v-old"
    assert pick_voice(grandma_persona, [], set()) is None


# --- live smoke (manual; needs a real key) -----------------------------------
@pytest.mark.skipif(not os.getenv("GRADIUM_API_KEY"), reason="needs GRADIUM_API_KEY")
async def test_live_exit_interview_produces_playable_wav(
    tmp_path, grandma_result, grandma_persona
):
    engine = GradiumVoiceEngine(os.environ["GRADIUM_API_KEY"], tmp_path)
    path = await engine.exit_interview(grandma_result, grandma_persona)
    with wave.open(path) as wav:
        assert wav.getnframes() > 0
