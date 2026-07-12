"""GradiumVoiceEngine — synthesize persona exit interviews with Gradium TTS.

Implements the frozen `VoiceEngine` protocol. Construction is cheap and never
touches the network or the Gradium SDK's connection layer; a `GradiumClient` is
created lazily the first time a synth method is actually called. If no API key is
available at that point, a clear error is raised (not on import/construction).

Verified against the installed `gradium` package:
  * `gradium.GradiumClient(api_key=...)`  (keyword-only; raises if no key)
  * `await client.tts(setup, text) -> TTSResult`  where
    `setup` is a `TTSSetup` dict, e.g. {"voice_id": <uid>, "output_format": "wav"}
    and `TTSResult.raw_data` holds the encoded audio bytes.
  * `await client.stt(setup, audio_bytes) -> STTResult` (`.text`) for the
    optional judge Q&A helper.
"""

from __future__ import annotations

import re
from pathlib import Path

import gradium

from ghostpanel_contracts import PersonaConfig, PersonaResult

from .narrate import write_exit_interview


def _fix_wav_header(audio: bytes) -> bytes:
    """Rewrite the RIFF/data chunk sizes from the actual byte length.

    Gradium's streamed WAVs carry placeholder sizes (0xFFFFFFFF-style), which
    makes players report absurd durations and breaks <audio> scrubbing."""
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return audio
    fixed = bytearray(audio)
    fixed[4:8] = (len(audio) - 8).to_bytes(4, "little")
    data_at = audio.find(b"data", 12)
    if data_at != -1 and data_at + 8 <= len(audio):
        fixed[data_at + 4:data_at + 8] = (len(audio) - data_at - 8).to_bytes(4, "little")
    return bytes(fixed)


class GradiumVoiceEngine:
    """Concrete `VoiceEngine`. See registry: constructed as
    ``GradiumVoiceEngine(api_key, artifact_dir, anthropic_key=None)``."""

    def __init__(
        self,
        api_key: str | None,
        artifact_dir: str | Path,
        anthropic_key: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._anthropic_key = anthropic_key
        self._artifact_dir = Path(artifact_dir)
        self._client: gradium.GradiumClient | None = None

    # -- internals --------------------------------------------------------
    def _get_client(self) -> "gradium.GradiumClient":
        """Lazily build the Gradium client; raise a clear error with no key."""
        if not self._api_key:
            raise RuntimeError(
                "GradiumVoiceEngine requires a Gradium API key to synthesize "
                "audio. Pass api_key=... (or set GRADIUM_API_KEY) before "
                "calling exit_interview()/mutter()."
            )
        if self._client is None:
            self._client = gradium.GradiumClient(api_key=self._api_key)
        return self._client

    @staticmethod
    def _tts_setup(voice_id: str | None) -> "gradium.TTSSetup":
        setup: gradium.TTSSetup = {"output_format": "wav"}
        if voice_id:
            setup["voice_id"] = voice_id
        return setup

    def _write_wav(self, name: str, audio: bytes) -> str:
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self._artifact_dir / f"{name}.wav"
        path.write_bytes(_fix_wav_header(audio))
        return str(path)

    # -- VoiceEngine protocol --------------------------------------------
    async def exit_interview(
        self, result: PersonaResult, persona: PersonaConfig
    ) -> str:
        """Generate the exit-interview text, synthesize it, write a .wav.

        Mutates the passed `result` in place: sets ``result.transcript`` and
        ``result.audio_path``. Returns the .wav path. Raises if no Gradium key.
        """
        # Fail fast (and without mutating) when we cannot synthesize.
        client = self._get_client()

        text = await write_exit_interview(
            result, persona, anthropic_key=self._anthropic_key
        )
        result.transcript = text

        voice_id = persona.voice_id
        tts_result = await client.tts(self._tts_setup(voice_id), text)
        path = self._write_wav(persona.id, tts_result.raw_data)
        result.audio_path = path
        return path

    async def mutter(self, text: str, voice_id: str | None) -> str:
        """Synthesize a short in-run one-liner; return its .wav path."""
        client = self._get_client()
        tts_result = await client.tts(self._tts_setup(voice_id), text)
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24] or "mutter"
        return self._write_wav(f"mutter-{slug}", tts_result.raw_data)

    # -- optional live-demo helper ---------------------------------------
    async def transcribe(self, audio_wav: bytes) -> str:
        """STT helper so a judge can ask a spoken question (optional demo path).

        Uses buffered `client.stt(setup, audio_bytes)`; returns the transcript.
        """
        client = self._get_client()
        setup: gradium.STTSetup = {"input_format": "wav"}
        stt_result = await client.stt(setup, audio_wav)
        return stt_result.text
