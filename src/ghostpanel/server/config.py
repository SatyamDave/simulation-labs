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
from typing import Optional

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

    # --- Hosted product (Phase 2+) ---
    # Async SQLAlchemy URL. Default: local SQLite file (dev/test). Prod overrides
    # with postgresql+asyncpg://...  Empty string => the sqlite default below.
    database_url: str = ""
    # HMAC secret for session JWTs. MUST be overridden in prod (loud check).
    session_secret: str = "dev-insecure-secret-change-me"
    session_ttl_hours: int = 720
    # Artifact storage backend: "local" (artifact_dir) or "s3".
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""      # for MinIO / S3-compatible; empty => AWS
    s3_region: str = ""
    s3_public_base_url: str = ""   # optional CDN/base for building artifact URLs
    # Number of concurrent swarm jobs a worker runs (keep small for the RPM cap).
    worker_concurrency: int = 1
    # --- Billing (Phase 4; test-mode until real keys) ---
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_team: str = ""

    # Deployment env: "dev" (default) or "production". Drives cookie-secure +
    # the boot-time refusal of the default session secret.
    env: str = "dev"

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() in ("production", "prod")

    @property
    def session_cookie_secure(self) -> bool:
        """Send the session cookie only over HTTPS in production."""
        return self.is_production

    @property
    def effective_database_url(self) -> str:
        """The async DB URL, defaulting to a repo-local SQLite file."""
        if self.database_url.strip():
            return self.database_url.strip()
        return f"sqlite+aiosqlite:///{_REPO_ROOT / 'ghostpanel.db'}"

    @property
    def has_stripe(self) -> bool:
        return bool(self.stripe_secret_key.strip())

    # --- NemoClaw / NVIDIA (optional stretch) ---
    nemoclaw_gateway_url: str = ""
    # OpenShell preset the swarm mirrors client-side (see runner.policy).
    # Resolved by get_settings(): env NEMOCLAW_POLICY_FILE, else the bundled
    # policies/ghostpanel-browse-only.yaml when it exists, else None.
    nemoclaw_policy_file: Optional[Path] = None

    @property
    def holo_base_url(self) -> str:
        """Effective Holo base URL — routed through the NemoClaw policy gateway
        when ``NEMOCLAW_GATEWAY_URL`` is set, else the direct Holo endpoint."""
        gw = self.nemoclaw_gateway_url.strip()
        return gw if gw else self.hai_base_url

    @property
    def has_gradium(self) -> bool:
        return bool(self.gradium_api_key.strip())


def _resolve_policy_file() -> Optional[Path]:
    """NEMOCLAW_POLICY_FILE from env, else the bundled browse-only preset if
    present, else None (no client-side mirror enforcement)."""
    raw = _get_str("NEMOCLAW_POLICY_FILE")
    if raw:
        return Path(raw).expanduser().resolve()
    default = _REPO_ROOT / "policies" / "ghostpanel-browse-only.yaml"
    return default if default.is_file() else None


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
        nemoclaw_policy_file=_resolve_policy_file(),
        database_url=_get_str("DATABASE_URL"),
        session_secret=_get_str("SESSION_SECRET", "dev-insecure-secret-change-me"),
        session_ttl_hours=_get_int("SESSION_TTL_HOURS", 720),
        storage_backend=_get_str("STORAGE_BACKEND", "local"),
        s3_bucket=_get_str("S3_BUCKET"),
        s3_endpoint_url=_get_str("S3_ENDPOINT_URL"),
        s3_region=_get_str("S3_REGION"),
        s3_public_base_url=_get_str("S3_PUBLIC_BASE_URL"),
        worker_concurrency=_get_int("WORKER_CONCURRENCY", 1),
        stripe_secret_key=_get_str("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=_get_str("STRIPE_WEBHOOK_SECRET"),
        stripe_price_team=_get_str("STRIPE_PRICE_TEAM"),
        env=_get_str("GHOSTPANEL_ENV", "dev"),
    )
