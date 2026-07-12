"""GradiumVoiceEngine — the concrete VoiceEngine (see CLAUDE.md registry).

exit_interview: real action trace -> first-person text (narrate.py) ->
Gradium TTS -> <artifact_dir>/<run_id or 'default'>/<persona_id>.wav, with
`result.transcript` / `result.audio_path` filled in as a side effect.
mutter: short one-liner TTS for in-run muttering.

Construction never needs a key (safe at import/wire time); a clear error is
raised only when synthesis is actually attempted without GRADIUM_API_KEY.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

from ghostpanel_contracts import PersonaConfig, PersonaResult

from ghostpanel.voice.narrate import write_exit_interview

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value).strip("-") or "unnamed"


class GradiumVoiceEngine:
    """Concrete VoiceEngine backed by the Gradium SDK.

    Args:
        api_key: Gradium key (gd-...). Falls back to GRADIUM_API_KEY env at
            synthesis time; missing entirely -> RuntimeError when synthesizing.
        artifact_dir: root artifact directory; wavs go under <run_id>/.
        anthropic_key: optional Claude key for narrated exit interviews
            (without it, narrate.py's deterministic grounded template is used).
    """

    def __init__(
        self,
        api_key: Optional[str],
        artifact_dir: str | Path,
        anthropic_key: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._artifact_dir = Path(artifact_dir)
        self._anthropic_key = anthropic_key
        self._client = None  # lazy: GradiumClient refuses to construct keyless
        self.run_id: Optional[str] = None  # orchestrator may set per run
        self.default_voice_id: Optional[str] = None  # e.g. from voices.assign_voices

    # -- client plumbing ----------------------------------------------------
    def _get_client(self):
        if self._client is not None:
            return self._client
        key = self._api_key or os.getenv("GRADIUM_API_KEY")
        if not key:
            raise RuntimeError(
                "Gradium API key missing: pass api_key to GradiumVoiceEngine or "
                "set GRADIUM_API_KEY before synthesizing audio."
            )
        from gradium import GradiumClient

        self._client = GradiumClient(api_key=key)
        return self._client

    def _tts_setup(self, voice_id: Optional[str]) -> dict:
        setup: dict = {"output_format": "wav"}
        if voice_id:
            setup["voice_id"] = voice_id
        else:
            setup["voice"] = "default"
        return setup

    async def _synthesize(self, text: str, voice_id: Optional[str], wav_path: Path) -> Path:
        client = self._get_client()
        result = await client.tts(setup=self._tts_setup(voice_id), text=text)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(result.raw_data)
        return wav_path

    # -- VoiceEngine protocol -------------------------------------------------
    async def exit_interview(self, result: PersonaResult, persona: PersonaConfig) -> str:
        """Narrate + synthesize the persona's exit interview; return .wav path.
        Sets result.transcript and result.audio_path as a side effect."""
        text = await write_exit_interview(result, persona, self._anthropic_key)
        result.transcript = text
        wav_path = (
            self._artifact_dir / (self.run_id or "default") / f"{_slug(persona.id)}.wav"
        )
        voice_id = persona.voice_id or self.default_voice_id
        await self._synthesize(text, voice_id, wav_path)
        result.audio_path = str(wav_path)
        return str(wav_path)

    async def mutter(self, text: str, voice_id: Optional[str]) -> str:
        """Synthesize a short in-run line; return the audio path."""
        digest = hashlib.sha1(f"{voice_id}:{text}".encode()).hexdigest()[:12]
        wav_path = self._artifact_dir / (self.run_id or "default") / "mutters" / f"{digest}.wav"
        await self._synthesize(text, voice_id or self.default_voice_id, wav_path)
        return str(wav_path)

    # -- optional live-demo helper --------------------------------------------
    async def transcribe(self, wav_bytes: bytes) -> str:
        """STT helper for live Q&A: transcribe a spoken question (.wav bytes)."""
        client = self._get_client()
        result = await client.stt(setup={"input_format": "wav"}, audio=wav_bytes)
        return result.text
