"""Assign a distinct Gradium voice_id to each persona.

Strategy (reliability first):
  1. Honor an explicit `persona.voice_id` if the config already sets one.
  2. Otherwise hand out DISTINCT preset voices from the Gradium catalog so no
     two personas sound alike.
  3. Optional: clone a bespoke voice from a short (~10s) sample via
     `client.voice_create(...)` — used only when a sample path is supplied.

This is async because the catalog lookup / clone are network calls. It degrades
gracefully: if the catalog can't be fetched, personas without an explicit
voice_id are left as ``None`` (the engine then uses the TTS default voice).
"""

from __future__ import annotations

import pathlib

from ghostpanel_contracts import PersonaConfig


def _extract_voice_ids(catalog: object) -> list[str]:
    """Pull a flat list of voice UIDs out of whatever shape voice_get returns."""
    ids: list[str] = []

    def _grab(item: object) -> None:
        if isinstance(item, dict):
            uid = item.get("uid") or item.get("voice_id") or item.get("id")
            if isinstance(uid, str):
                ids.append(uid)

    if isinstance(catalog, dict):
        # Common shapes: {"voices": [...]} or {"default": [...], "custom": [...]}
        for value in catalog.values():
            if isinstance(value, list):
                for item in value:
                    _grab(item)
            else:
                _grab(value)
        _grab(catalog)
    elif isinstance(catalog, list):
        for item in catalog:
            _grab(item)

    # de-dup, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for uid in ids:
        if uid and uid not in seen:
            seen.add(uid)
            out.append(uid)
    return out


async def assign_voices(
    personas: list[PersonaConfig],
    client: object,
    clone_samples: dict[str, pathlib.Path] | None = None,
) -> dict[str, str]:
    """Return ``{persona_id: voice_id}`` for personas we could resolve.

    `clone_samples` optionally maps ``persona_id -> audio_file`` to clone a
    bespoke voice for that persona instead of using a preset.
    """
    clone_samples = clone_samples or {}
    mapping: dict[str, str] = {}

    # 1. explicit voice_ids win outright
    remaining: list[PersonaConfig] = []
    for persona in personas:
        if persona.voice_id:
            mapping[persona.id] = persona.voice_id
        else:
            remaining.append(persona)

    # 2. optional clones from samples
    still: list[PersonaConfig] = []
    for persona in remaining:
        sample = clone_samples.get(persona.id)
        if sample is not None:
            try:
                created = await client.voice_create(
                    pathlib.Path(sample), name=f"ghostpanel-{persona.id}"
                )
                uid = created.get("uid") if isinstance(created, dict) else None
                if uid:
                    mapping[persona.id] = uid
                    continue
            except Exception:
                pass  # fall through to preset
        still.append(persona)

    if not still:
        return mapping

    # 3. distinct presets from the catalog
    presets: list[str] = []
    try:
        catalog = await client.voice_get(include_catalog=True)
        presets = _extract_voice_ids(catalog)
    except Exception:
        presets = []

    for i, persona in enumerate(still):
        if presets:
            mapping[persona.id] = presets[i % len(presets)]
        # else: leave unassigned -> engine uses default voice

    return mapping
