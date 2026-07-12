"""Ghostpanel memory layer.

Public surface (import from here, not from submodules):

  * ``MemoryStore``        — the Protocol every consumer depends on
  * ``NullMemoryStore``    — no-op default when Supermemory is unconfigured
  * ``create_memory_store``— composition-root factory (live or null)
  * ``InsightRecord``      — derived response type for GET /insights
  * mode constants + tag/impairment helpers

The live ``SupermemoryStore`` is intentionally NOT re-exported here so importing
``ghostpanel.memory`` never pulls in the ``supermemory`` SDK. Use the factory.
"""

from __future__ import annotations

from .store import (
    DEFAULT_MODE,
    INSIGHTS_TAG,
    MODE_OFF,
    MODE_RETURNING_USER,
    MODE_SITE_HINTS,
    VALID_MODES,
    InsightRecord,
    MemoryStore,
    NullMemoryStore,
    create_memory_store,
    domain_slug,
    impairment_key,
    normalize_mode,
    persona_site_tag,
    site_tag,
)

__all__ = [
    "DEFAULT_MODE",
    "INSIGHTS_TAG",
    "MODE_OFF",
    "MODE_RETURNING_USER",
    "MODE_SITE_HINTS",
    "VALID_MODES",
    "InsightRecord",
    "MemoryStore",
    "NullMemoryStore",
    "create_memory_store",
    "domain_slug",
    "impairment_key",
    "normalize_mode",
    "persona_site_tag",
    "site_tag",
]
