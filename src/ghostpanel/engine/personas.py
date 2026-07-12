"""Persona loader — reads personas/*.json into validated PersonaConfig objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ghostpanel_contracts import PersonaConfig

# personas/ lives at the repo root: src/ghostpanel/engine/personas.py -> up 4.
_PERSONA_DIR = Path(__file__).resolve().parents[3] / "personas"


def personas_dir() -> Path:
    """Directory containing the persona JSON files."""
    return _PERSONA_DIR


def load_personas(ids: Optional[list[str]] = None) -> list[PersonaConfig]:
    """Load and validate every ``personas/*.json`` file.

    Args:
        ids: if given, keep only personas whose ``id`` is in this list, ordered to
             match ``ids``. Unknown ids are silently skipped.

    Returns:
        A list of PersonaConfig, sorted by id for determinism (unless filtered by
        ``ids``, in which case the ``ids`` order is preserved).
    """
    directory = _PERSONA_DIR
    configs: dict[str, PersonaConfig] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            cfg = PersonaConfig.model_validate(data)
            if cfg.id in configs:
                raise ValueError(f"Duplicate persona id '{cfg.id}' in {path.name}")
            configs[cfg.id] = cfg

    if ids is not None:
        return [configs[i] for i in ids if i in configs]
    return [configs[k] for k in sorted(configs)]
