"""Model-backend registry — the seam that keeps inference vendor-agnostic.

``build_model(name, settings)`` returns a ``HoloClient`` for a backend name.
This is the ONE place that knows how to construct each concrete inference client,
so we can swap or scale vendors (add a new backend, route through a gateway, drop
in a local model) WITHOUT touching the runner or the worker — they only ever ask
for a ``HoloClient`` by name.

Backends:
    * ``"holo"`` — the real H-Company Holo Models API (``LiveHoloClient``); the
      default and production backend.
    * ``"selfhost"`` — a self-hosted vLLM endpoint serving the SAME Holo weights
      (``SelfHostedHoloClient``). Vendor-independent, no shared RPM cap. Point
      ``HAI_BASE_URL`` at your vLLM ``/v1``. See ``docs/SELF_HOSTING.md``.
    * ``"echo"`` — a trivial, deterministic, offline backend (``EchoModelClient``)
      that proves a non-Holo vendor plugs into the same seam.
    * ``"gemini"`` — Google Gemini via its OpenAI-compatible endpoint
      (``GeminiClient``). Same 0-1000 coordinate grid as Holo; prompts are
      rewritten to say so explicitly. Reads ``GEMINI_API_KEY`` / ``GEMINI_MODEL``
      / ``GEMINI_BASE_URL`` / ``GEMINI_RPM`` from the environment.
"""

from __future__ import annotations

import os

from ghostpanel_contracts import HoloClient

from ..gemini_client import (
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MAX_CONCURRENCY,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_RPM,
    GeminiClient,
)
from ..holo_client import LiveHoloClient
from ..selfhost_client import (
    DEFAULT_SELFHOST_BASE_URL,
    UNCAPPED_RPM,
    SelfHostedHoloClient,
)
from .echo import EchoModelClient

# Registered backend names (kept in sync with the branches in ``build_model``).
_BACKENDS = ("holo", "selfhost", "echo", "gemini")


def available() -> list[str]:
    """Return the list of registered model-backend names."""
    return list(_BACKENDS)


def default_backend() -> str:
    """The backend to use when none is specified.

    Reads the ``MODEL_BACKEND`` environment variable (default ``"holo"``) so the
    default can be flipped for CI/offline runs without any Settings change.
    """
    return os.environ.get("MODEL_BACKEND", "holo")


def build_model(name: str, settings) -> HoloClient:
    """Construct the ``HoloClient`` for backend ``name`` using ``settings``.

    Args:
        name: a registered backend name (see ``available()``).
        settings: a ``server.config.Settings`` (or any object exposing the same
            ``hai_api_key`` / ``holo_base_url`` / ``hai_model`` / ``hai_rpm``
            attributes) — only read for the ``"holo"`` backend.

    Raises:
        ValueError: if ``name`` is not a registered backend.
    """
    key = (name or "").strip().lower()
    if key == "holo":
        return LiveHoloClient(
            api_key=settings.hai_api_key,
            base_url=settings.holo_base_url,
            model=settings.hai_model,
            rpm=settings.hai_rpm,
        )
    if key == "selfhost":
        # Same weights, same 0-1000 coordinate grid as "holo", but pointed at a
        # self-hosted vLLM endpoint and with no vendor RPM cap. Reuses the base
        # URL from settings (set HAI_BASE_URL to your vLLM /v1). If it still
        # points at the hosted vendor default, fall back to the local default so
        # a mis-set env doesn't silently hit the capped vendor API.
        base_url = settings.holo_base_url
        if not base_url or "hcompany.ai" in base_url:
            base_url = DEFAULT_SELFHOST_BASE_URL
        # Honour an explicitly-high HAI_RPM as a self-imposed throttle; otherwise
        # leave the cap effectively disabled (SelfHostedHoloClient's default).
        rpm = settings.hai_rpm if (settings.hai_rpm and settings.hai_rpm > 100) else UNCAPPED_RPM
        return SelfHostedHoloClient(
            api_key=settings.hai_api_key,
            base_url=base_url,
            model=settings.hai_model,
            rpm=rpm,
        )
    if key == "echo":
        return EchoModelClient()
    if key == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "MODEL_BACKEND=gemini requires GEMINI_API_KEY in the environment "
                "(.env). Create one at https://aistudio.google.com/apikey"
            )
        try:
            rpm = float(os.environ.get("GEMINI_RPM", "") or DEFAULT_GEMINI_RPM)
        except ValueError:
            rpm = DEFAULT_GEMINI_RPM
        try:
            conc = int(os.environ.get("GEMINI_MAX_CONCURRENCY", "")
                       or DEFAULT_GEMINI_MAX_CONCURRENCY)
        except ValueError:
            conc = DEFAULT_GEMINI_MAX_CONCURRENCY
        return GeminiClient(
            api_key=api_key,
            base_url=os.environ.get("GEMINI_BASE_URL", "").strip()
            or DEFAULT_GEMINI_BASE_URL,
            model=os.environ.get("GEMINI_MODEL", "").strip()
            or DEFAULT_GEMINI_MODEL,
            rpm=rpm,
            max_concurrency=conc,
        )
    raise ValueError(
        f"Unknown model backend {name!r}. Available: {', '.join(available())}"
    )
