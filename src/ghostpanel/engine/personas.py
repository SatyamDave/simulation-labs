"""Persona loader (Agent 1): personas/*.json -> validated PersonaConfig list."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ghostpanel_contracts import PersonaConfig

# <repo>/src/ghostpanel/engine/personas.py -> <repo>/personas
PERSONAS_DIR = Path(__file__).resolve().parents[3] / "personas"


def load_personas(
    ids: Optional[list[str]] = None,
    personas_dir: Optional[Path] = None,
) -> list[PersonaConfig]:
    """Load every ``personas/*.json`` (sorted by filename) as a PersonaConfig.

    ``ids`` filters (and orders) the result; an unknown id raises ``KeyError``
    so typos fail loudly instead of silently shrinking the swarm.
    """
    directory = Path(personas_dir) if personas_dir is not None else PERSONAS_DIR
    configs = [
        PersonaConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
    ]
    if ids is None:
        return configs
    by_id = {c.id: c for c in configs}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise KeyError(f"Unknown persona id(s): {missing}; available: {sorted(by_id)}")
    return [by_id[i] for i in ids]
