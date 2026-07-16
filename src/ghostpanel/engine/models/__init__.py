"""Pluggable model-backend registry for Ghostpanel's inference layer.

This package is the seam that lets us swap or scale the inference vendor behind
the frozen ``HoloClient`` contract WITHOUT touching the runner or worker. The
runner/worker ask the registry for a ``HoloClient`` by name (``build_model``);
they never construct a concrete client directly.

Public API:
    * ``build_model(name, settings) -> HoloClient``
    * ``available() -> list[str]``
    * ``default_backend() -> str``   (reads ``MODEL_BACKEND``, defaults ``"holo"``)
    * ``EchoModelClient``            (a trivial, offline, non-Holo backend)
"""

from __future__ import annotations

from .echo import EchoModelClient
from .registry import available, build_model, default_backend

__all__ = ["build_model", "available", "default_backend", "EchoModelClient"]
