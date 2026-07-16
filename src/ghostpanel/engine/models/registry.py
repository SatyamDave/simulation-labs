"""Model-backend registry — the seam that keeps inference vendor-agnostic.

``build_model(name, settings)`` returns a ``HoloClient`` for a backend name.
This is the ONE place that knows how to construct each concrete inference client,
so we can swap or scale vendors (add a new backend, route through a gateway, drop
in a local model) WITHOUT touching the runner or the worker — they only ever ask
for a ``HoloClient`` by name.

Backends:
    * ``"holo"`` — the real H-Company Holo Models API (``LiveHoloClient``); the
      default and production backend.
    * ``"echo"`` — a trivial, deterministic, offline backend (``EchoModelClient``)
      that proves a non-Holo vendor plugs into the same seam.
"""

from __future__ import annotations

import os

from ghostpanel_contracts import HoloClient

from ..holo_client import LiveHoloClient
from .echo import EchoModelClient

# Registered backend names (kept in sync with the branches in ``build_model``).
_BACKENDS = ("holo", "echo")


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
    if key == "echo":
        return EchoModelClient()
    raise ValueError(
        f"Unknown model backend {name!r}. Available: {', '.join(available())}"
    )
