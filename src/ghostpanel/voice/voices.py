"""Assign each persona a distinct Gradium voice.

Prefers distinct *preset* voices from the Gradium catalog (reliable), scored
against persona traits — the grandmother should get the oldest-sounding voice
available, the impatient one something quick and clipped. A persona whose
config already pins `voice_id` keeps it. Cloning from a short audio sample is
available via `clone_voice` (uses the SDK's voice-create endpoint).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghostpanel_contracts import PersonaConfig

# Trait keywords looked for in the persona's id/name/blurb, mapped to keywords
# scored against Gradium voice names/descriptions. Order = priority.
_TRAIT_TO_VOICE_KEYWORDS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("grandma", "grandpa", "elder", "senior", "70", "72", "old"),
     ("old", "elder", "grand", "senior", "mature", "warm", "aged")),
    (("impatient", "hurry", "busy", "rushed"),
     ("fast", "energetic", "clipped", "sharp", "young", "dynamic")),
    (("low vision", "low-vision", "blind", "vision"),
     ("calm", "soft", "gentle", "measured")),
    (("tremor", "motor", "parkinson"),
     ("deep", "steady", "slow", "calm")),
    (("kid", "teen", "young", "student"),
     ("young", "bright", "light")),
    (("agent", "ai", "bot", "headless"),
     ("neutral", "robot", "synthetic", "flat", "narrator")),
]


def _flatten_catalog(catalog: Any) -> list[dict]:
    """voice_get() returns either a list of voices or a dict of category->list;
    normalize to a flat list of {uid, name, description} dicts."""
    if isinstance(catalog, list):
        entries = catalog
    elif isinstance(catalog, dict):
        entries = []
        for value in catalog.values():
            if isinstance(value, list):
                entries.extend(value)
    else:
        entries = []
    return [e for e in entries if isinstance(e, dict) and e.get("uid")]


def _voice_keywords_for(persona: PersonaConfig) -> tuple[str, ...]:
    haystack = f"{persona.id} {persona.name} {persona.blurb}".lower()
    for traits, keywords in _TRAIT_TO_VOICE_KEYWORDS:
        if any(t in haystack for t in traits):
            return keywords
    return ()


def _score(voice: dict, keywords: tuple[str, ...]) -> int:
    text = f"{voice.get('name', '')} {voice.get('description', '')}".lower()
    return sum(1 for kw in keywords if kw in text)


def pick_voice(
    persona: PersonaConfig, available: list[dict], used: set[str]
) -> str | None:
    """Pure selection logic (unit-testable without a network): best keyword
    match among unused voices, falling back to any unused voice, then to the
    overall best match even if reused."""
    if persona.voice_id:
        return persona.voice_id
    if not available:
        return None
    keywords = _voice_keywords_for(persona)
    ranked = sorted(available, key=lambda v: _score(v, keywords), reverse=True)
    for voice in ranked:
        if voice["uid"] not in used:
            return voice["uid"]
    return ranked[0]["uid"]  # more personas than voices: reuse the best fit


async def assign_voices(personas: list[PersonaConfig], client) -> dict[str, str]:
    """Map persona_id -> Gradium voice_id, keeping voices distinct while the
    catalog lasts. `client` is a gradium.GradiumClient."""
    catalog = _flatten_catalog(await client.voice_get(include_catalog=True))
    used: set[str] = set()
    assignment: dict[str, str] = {}
    for persona in personas:
        voice_id = pick_voice(persona, catalog, used)
        if voice_id is not None:
            assignment[persona.id] = voice_id
            used.add(voice_id)
    return assignment


async def clone_voice(client, audio_file: str | Path, name: str) -> str:
    """Clone a voice from a ~10s audio sample; returns the new voice uid."""
    created = await client.voice_create(Path(audio_file), name=name)
    return created["uid"]
