"""Environment configuration for the Ghostpanel orchestrator.

Loads ``.env`` (via python-dotenv) and exposes a frozen ``Settings`` dataclass
holding every knob the composition root needs. Never hardcode secrets — all keys
come from the environment. See ``.env.example`` for the full list of names.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# repo root: src/ghostpanel/server/config.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_env() -> None:
    """Load the repo-root .env if present, else fall back to dotenv's search."""
    env_path = _REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    return raw if raw not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration for the server + swarm."""

    # --- Holo Models API (Agent 1) ---
    hai_api_key: str = ""
    hai_base_url: str = "https://api.hcompany.ai/v1/"
    hai_model: str = "holo3-1-35b-a3b"
    hai_rpm: float = 5.0

    # --- Gradium voice (Agent 5) ---
    gradium_api_key: str = ""

    # --- Anthropic (exit-interview narration, Agent 5) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    artifact_dir: Path = _REPO_ROOT / "artifacts"

    # --- NemoClaw / NVIDIA (optional stretch) ---
    nemoclaw_gateway_url: str = ""

    @property
    def holo_base_url(self) -> str:
        """Effective Holo base URL — routed through the NemoClaw policy gateway
        when ``NEMOCLAW_GATEWAY_URL`` is set, else the direct Holo endpoint."""
        gw = self.nemoclaw_gateway_url.strip()
        return gw if gw else self.hai_base_url

    @property
    def has_gradium(self) -> bool:
        return bool(self.gradium_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build (and cache) the Settings from the environment / .env."""
    _load_env()
    artifact_dir = _get_str("GHOSTPANEL_ARTIFACT_DIR", str(_REPO_ROOT / "artifacts"))
    return Settings(
        hai_api_key=_get_str("HAI_API_KEY"),
        hai_base_url=_get_str("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
        hai_model=_get_str("HAI_MODEL", "holo3-1-35b-a3b"),
        hai_rpm=_get_float("HAI_RPM", 5.0),
        gradium_api_key=_get_str("GRADIUM_API_KEY"),
        anthropic_api_key=_get_str("ANTHROPIC_API_KEY"),
        anthropic_model=_get_str("ANTHROPIC_MODEL", "claude-sonnet-5"),
        host=_get_str("GHOSTPANEL_HOST", "127.0.0.1"),
        port=_get_int("GHOSTPANEL_PORT", 8000),
        artifact_dir=Path(artifact_dir).expanduser().resolve(),
        nemoclaw_gateway_url=_get_str("NEMOCLAW_GATEWAY_URL"),
    )
