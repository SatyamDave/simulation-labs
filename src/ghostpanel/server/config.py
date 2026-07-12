"""Ghostpanel server configuration.

All settings come from the environment (optionally seeded from a `.env` file
via python-dotenv). Names mirror `.env.example` exactly. Nothing here imports
any other ghostpanel module, so it is safe to import anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    """Typed view over the Ghostpanel environment variables."""

    # --- H Company Holo Models API (shared by the whole swarm) ---
    hai_api_key: str = ""
    hai_base_url: str = "https://api.hcompany.ai/v1/"
    hai_model: str = "holo3-1-35b-a3b"
    hai_rpm: int = 10

    # --- Gradium voice ---
    gradium_api_key: str = ""

    # --- Anthropic (exit-interview scripting) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    artifact_dir: Path = field(default_factory=lambda: Path("./artifacts"))

    # --- NemoClaw / NVIDIA policy gateway (optional stretch) ---
    nemoclaw_gateway_url: str = ""

    @property
    def holo_base_url(self) -> str:
        """Base URL the shared Holo client should hit.

        When NEMOCLAW_GATEWAY_URL is set, Holo inference is routed through the
        OpenShell policy gateway instead of calling Holo directly.
        """
        return self.nemoclaw_gateway_url or self.hai_base_url

    @classmethod
    def from_env(cls, env_file: str | os.PathLike[str] | None = ".env") -> "Settings":
        """Build Settings from os.environ, optionally loading a .env file first."""
        if env_file is not None:
            load_dotenv(env_file, override=False)

        def _get(name: str, default: str) -> str:
            value = os.environ.get(name, "").strip()
            return value or default

        return cls(
            hai_api_key=_get("HAI_API_KEY", ""),
            hai_base_url=_get("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
            hai_model=_get("HAI_MODEL", "holo3-1-35b-a3b"),
            hai_rpm=int(_get("HAI_RPM", "10")),
            gradium_api_key=_get("GRADIUM_API_KEY", ""),
            anthropic_api_key=_get("ANTHROPIC_API_KEY", ""),
            anthropic_model=_get("ANTHROPIC_MODEL", "claude-sonnet-5"),
            host=_get("GHOSTPANEL_HOST", "127.0.0.1"),
            port=int(_get("GHOSTPANEL_PORT", "8000")),
            artifact_dir=Path(_get("GHOSTPANEL_ARTIFACT_DIR", "./artifacts")),
            nemoclaw_gateway_url=_get("NEMOCLAW_GATEWAY_URL", ""),
        )
