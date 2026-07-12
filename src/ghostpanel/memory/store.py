"""Ghostpanel memory layer — the shared seam.

This module is the *contract* between the memory implementation (Supermemory-backed,
in ``supermemory_store.py``) and every consumer (the orchestrator in
``server/``). It deliberately imports nothing from the ``supermemory`` package at
module load so that:

  * the no-op path works even when the SDK / an API key is absent, and
  * the existing test suite stays green with zero new dependencies.

Three kinds of memory, all partitioned by Supermemory *container tags* (each tag is
a physically isolated vector namespace):

  1. **Site playbooks** — ``gp:site:{domain}`` — distilled "what worked / what
     blocked" hints for a target site+task, recalled at run start to make the swarm
     more efficient (fewer steps ⇒ fewer screenshots sent to Holo ⇒ lower token cost).
  2. **Cross-run insights** — ``gp:insights`` — one record per abandonment, keyed by
     impairment category, powering the longitudinal "which UX patterns kill which
     impaired users across every site" knowledge base (GET /insights).
  3. **Returning-user memory** — ``gp:persona:{id}:site:{domain}`` — a persona's own
     recollection of its prior visits (first-time vs returning-user research mode).

MEMORY MODES (per run, chosen by the caller):
  * ``off``            — no recall injected. The scientifically-honest default: the
                         swarm behaves as genuine first-time impaired users, so
                         survival curves measure the *site*, not our memory.
  * ``site_hints``     — inject site-playbook hints (demo / regression runs).
  * ``returning_user`` — inject site hints + this persona's own past-visit memory.

Writes always happen regardless of mode (a run is always worth remembering); only
*recall injection* is gated by the mode.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

from ghostpanel_contracts import PersonaConfig, RunReport

# --- memory modes -----------------------------------------------------------
MODE_OFF = "off"
MODE_SITE_HINTS = "site_hints"
MODE_RETURNING_USER = "returning_user"
VALID_MODES = frozenset({MODE_OFF, MODE_SITE_HINTS, MODE_RETURNING_USER})
DEFAULT_MODE = MODE_OFF


def normalize_mode(mode: Optional[str]) -> str:
    """Coerce an arbitrary input to a valid mode, defaulting to ``off``."""
    if mode is None:
        return DEFAULT_MODE
    m = str(mode).strip().lower()
    return m if m in VALID_MODES else DEFAULT_MODE


# --- container-tag scheme (shared by the store AND the insights endpoint) ----
INSIGHTS_TAG = "gp:insights"

# Supermemory rejects container tags longer than 100 chars (HTTP 400 too_big).
_MAX_TAG = 100


def _cap_tag(tag: str) -> str:
    """Guarantee a container tag is <=100 chars (Supermemory's hard limit).

    Short tags (normal domains) pass through unchanged. Over-long tags — long
    hostnames, or ``file://`` fixture paths — are deterministically truncated and
    disambiguated with an 8-char hash of the full tag so distinct inputs never
    collide. Deterministic, so a write and a later recall produce the same tag."""
    if len(tag) <= _MAX_TAG:
        return tag
    digest = hashlib.sha1(tag.encode("utf-8")).hexdigest()[:8]
    return tag[: _MAX_TAG - 9].rstrip("-:") + "-" + digest


def domain_slug(url: str) -> str:
    """Stable, tag-safe slug for a URL's host, e.g. ``https://www.Stripe.com/x``
    -> ``stripe-com``. Falls back to a slug of the whole string for non-URLs
    (e.g. a local ``file://`` fixture path) so a tag is always producible."""
    try:
        netloc = urlparse(url).netloc or urlparse(url).path
    except Exception:  # noqa: BLE001 - never raise from a tag helper
        netloc = url
    netloc = netloc.strip().lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Drop port, keep alnum + dots -> hyphens.
    netloc = netloc.split(":", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", netloc).strip("-")
    return slug or "unknown"


def site_tag(url: str) -> str:
    """Container tag for a site's shared playbook (always <=100 chars)."""
    return _cap_tag(f"gp:site:{domain_slug(url)}")


def persona_site_tag(persona_id: str, url: str) -> str:
    """Container tag for one persona's private memory of one site (<=100 chars)."""
    pid = re.sub(r"[^a-z0-9]+", "-", persona_id.strip().lower()).strip("-") or "unknown"
    return _cap_tag(f"gp:persona:{pid}:site:{domain_slug(url)}")


def impairment_key(persona: PersonaConfig) -> str:
    """A stable impairment-category key for a persona, derived from its active
    perturbations (e.g. ``blur+low_literacy+tremor``). ``none`` for a baseline
    persona with no perturbations (power-user / ai-agent)."""
    perts = getattr(persona, "active_perturbations", None) or []
    names = sorted(str(getattr(p, "value", p)) for p in perts)
    return "+".join(names) if names else "none"


# --- records ----------------------------------------------------------------
@dataclass(frozen=True)
class InsightRecord:
    """A single distilled cross-run insight, as returned by ``recall_insights``.

    This is a *derived* response type — NOT a frozen contract — so the insights
    endpoint can shape it freely without an orchestrator contract change.
    """

    content: str
    site: str = ""
    persona_id: str = ""
    persona_name: str = ""
    impairment: str = ""
    outcome: str = ""
    steps_survived: Optional[int] = None
    score: Optional[float] = None
    metadata: dict = field(default_factory=dict)


# --- the seam ---------------------------------------------------------------
@runtime_checkable
class MemoryStore(Protocol):
    """What the orchestrator depends on. Implemented by ``SupermemoryStore``
    (live) and ``NullMemoryStore`` (no-op). Every method must be safe to call
    concurrently and must NEVER raise into the run loop — recall degrades to
    ``[]`` and writes degrade to ``0`` on any backend failure."""

    async def recall_hints(
        self,
        *,
        target_url: str,
        task: str,
        persona: PersonaConfig,
        mode: str,
    ) -> list[str]:
        """Return short natural-language hint lines to prepend to this persona's
        task, honoring ``mode``. ``[]`` when mode is ``off`` or nothing is known."""
        ...

    async def remember_run(
        self,
        *,
        run_id: str,
        target_url: str,
        task: str,
        report: RunReport,
        personas: list[PersonaConfig],
    ) -> int:
        """Persist site playbooks + cross-run insights from a finished run.
        Returns the number of memory records written (0 on no-op / failure)."""
        ...

    async def recall_insights(
        self,
        *,
        query: str,
        limit: int = 10,
        impairment: Optional[str] = None,
    ) -> list[InsightRecord]:
        """Query the cross-run insight knowledge base (powers GET /insights)."""
        ...

    async def aclose(self) -> None:
        """Release any underlying client/session. Idempotent."""
        ...


class NullMemoryStore:
    """No-op store used when Supermemory is not configured. Keeps the whole
    feature invisible (and the test suite offline) when no API key is present."""

    async def recall_hints(
        self,
        *,
        target_url: str,
        task: str,
        persona: PersonaConfig,
        mode: str,
    ) -> list[str]:
        return []

    async def remember_run(
        self,
        *,
        run_id: str,
        target_url: str,
        task: str,
        report: RunReport,
        personas: list[PersonaConfig],
    ) -> int:
        return 0

    async def recall_insights(
        self,
        *,
        query: str,
        limit: int = 10,
        impairment: Optional[str] = None,
    ) -> list[InsightRecord]:
        return []

    async def aclose(self) -> None:
        return None


def create_memory_store(
    *,
    api_key: str = "",
    base_url: str = "",
    anthropic_key: str = "",
    default_mode: str = DEFAULT_MODE,
) -> MemoryStore:
    """Composition-root factory. Returns a live ``SupermemoryStore`` when an API
    key is present, else a ``NullMemoryStore``. The live import is lazy so the
    ``supermemory`` package is only required when actually configured."""
    if not (api_key or "").strip():
        return NullMemoryStore()
    from .supermemory_store import SupermemoryStore  # lazy: avoids hard dep

    return SupermemoryStore(
        api_key=api_key,
        base_url=base_url,
        anthropic_key=anthropic_key,
        default_mode=normalize_mode(default_mode),
    )
