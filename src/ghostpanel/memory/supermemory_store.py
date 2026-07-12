"""Live Supermemory-backed implementation of the ``MemoryStore`` seam.

This is the only module that imports the ``supermemory`` SDK. Everything it does
degrades safely: recall failures return ``[]`` and write failures return ``0`` —
no backend error ever escapes into the run loop (the Protocol's hard invariant).

Ingestion in Supermemory is asynchronous (a written memory becomes searchable
~12–20 s later, no SLA). Our architecture never reads what it just wrote within a
run — ``remember_run`` writes at run-end, ``recall_hints`` reads at the start of a
FUTURE run — so writes are fire-and-forget (``dreaming="instant"`` just minimizes
time-to-searchable). See ``store.py`` for the container-tag scheme and modes.
"""

from __future__ import annotations

from typing import Optional

from ghostpanel_contracts import PersonaConfig, RunReport

from .distill import distill_run
from .store import (
    INSIGHTS_TAG,
    MODE_OFF,
    MODE_RETURNING_USER,
    InsightRecord,
    normalize_mode,
    persona_site_tag,
    site_tag,
)

# The SDK is a hard dependency of THIS module only (the factory imports it lazily
# and only when an API key is configured), so a top-level import is correct here.
from supermemory import (  # noqa: E402
    APIError,
    AsyncSupermemory,
)

# The SDK's own default. We pass base_url EXPLICITLY (always) rather than letting
# the SDK read it from the environment, because a blank ``SUPERMEMORY_BASE_URL=``
# in a .env resolves to "" (not None) and the SDK then sends a protocol-less URL
# (``httpx.UnsupportedProtocol``) instead of falling back to this default.
_DEFAULT_BASE_URL = "https://api.supermemory.ai"

# Tuning knobs — kept module-local so they never leak into the frozen seam.
_HINT_LIMIT = 4          # hits per site/persona search for recall_hints
_HINT_MAX = 5            # total hint lines returned (after de-dup)
_HINT_CHARS = 220        # per-hint character cap
_SEARCH_THRESHOLD = 0.5  # similarity floor (server default is 0.6)


def _result_text(r: object) -> str:
    """Pull the memory text out of a search result row, defensively.

    Result rows are pydantic models with a ``memory``/``chunk``/``content`` field,
    but some SDK rows are dict-like — handle both, and never raise."""
    for attr in ("memory", "chunk", "content"):
        val = getattr(r, attr, None)
        if val:
            return str(val)
    if isinstance(r, dict):
        for key in ("memory", "chunk", "content"):
            val = r.get(key)
            if val:
                return str(val)
    return ""


def _result_similarity(r: object) -> Optional[float]:
    """Extract the similarity score (there is no field literally named ``score``)."""
    val = getattr(r, "similarity", None)
    if val is None and isinstance(r, dict):
        val = r.get("similarity")
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _result_metadata(r: object) -> dict:
    """Extract the flat metadata dict attached to a result row."""
    meta = getattr(r, "metadata", None)
    if meta is None and isinstance(r, dict):
        meta = r.get("metadata")
    return dict(meta) if isinstance(meta, dict) else {}


def _shorten(text: str, limit: int = _HINT_CHARS) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


class SupermemoryStore:
    """Satisfies the ``MemoryStore`` Protocol (see ``store.py``)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "",
        anthropic_key: str = "",
        default_mode: str = MODE_OFF,
    ) -> None:
        self._anthropic_key = anthropic_key or ""
        self._default_mode = normalize_mode(default_mode)
        # Always pass base_url explicitly so a blank env var can never poison it.
        resolved_base_url = (base_url or "").strip() or _DEFAULT_BASE_URL
        # The SDK auto-retries 429/5xx (max_retries=2) with backoff — no own limiter.
        self._client = AsyncSupermemory(api_key=api_key, base_url=resolved_base_url)
        self._closed = False

    # -- internal search helper -------------------------------------------------
    async def _search(self, *, q: str, container_tag: str, limit: int) -> list:
        """Run one memories search; return the raw result rows or [] on any error."""
        try:
            resp = await self._client.search.memories(
                q=q,
                container_tag=container_tag,
                limit=limit,
                rerank=True,
                threshold=_SEARCH_THRESHOLD,
            )
        except (APIError, Exception):  # noqa: BLE001 - never raise into the caller
            return []
        return list(getattr(resp, "results", []) or [])

    # -- Protocol methods -------------------------------------------------------
    async def recall_hints(
        self,
        *,
        target_url: str,
        task: str,
        persona: PersonaConfig,
        mode: str,
    ) -> list[str]:
        mode = normalize_mode(mode)
        if mode == MODE_OFF:
            return []

        q = task or "how to complete this task"
        hints: list[str] = []

        # Returning-user: this persona's OWN memories lead (most personal signal).
        if mode == MODE_RETURNING_USER:
            rows = await self._search(
                q=q,
                container_tag=persona_site_tag(persona.id, target_url),
                limit=_HINT_LIMIT,
            )
            hints.extend(_shorten(_result_text(r)) for r in rows)

        # Shared site playbook (both non-off modes).
        rows = await self._search(
            q=q, container_tag=site_tag(target_url), limit=_HINT_LIMIT
        )
        hints.extend(_shorten(_result_text(r)) for r in rows)

        # De-dup preserving order; drop empties; cap total.
        seen: set[str] = set()
        out: list[str] = []
        for h in hints:
            if h and h not in seen:
                seen.add(h)
                out.append(h)
            if len(out) >= _HINT_MAX:
                break
        return out

    async def remember_run(
        self,
        *,
        run_id: str,
        target_url: str,
        task: str,
        report: RunReport,
        personas: list[PersonaConfig],
    ) -> int:
        try:
            records = distill_run(
                target_url=target_url,
                task=task,
                report=report,
                personas=personas,
                run_id=run_id,
            )
        except Exception:  # noqa: BLE001 - distillation must never abort a run
            return 0

        written = 0
        for rec in records:
            # Deterministic id so a retried run doesn't duplicate memories.
            pid = rec.metadata.get("persona_id", "?")
            custom_id = f"{run_id}:{pid}:{rec.custom_id_kind}"
            try:
                await self._client.documents.add(
                    content=rec.content,
                    container_tags=rec.container_tags,
                    metadata=rec.metadata,
                    dreaming="instant",
                    custom_id=custom_id,
                )
                written += 1
            except (APIError, Exception):  # noqa: BLE001 - one failure ≠ abort the rest
                continue
        return written

    async def recall_insights(
        self,
        *,
        query: str,
        limit: int = 10,
        impairment: Optional[str] = None,
    ) -> list[InsightRecord]:
        q = query.strip() if query else ""
        if not q:
            q = "abandonment usability accessibility"

        # When filtering by impairment, over-fetch and filter in Python: the SDK's
        # filter shape is intricate (AND/OR trees) and correctness beats cleverness.
        fetch = limit * 4 if impairment else limit
        rows = await self._search(q=q, container_tag=INSIGHTS_TAG, limit=fetch)

        out: list[InsightRecord] = []
        for r in rows:
            meta = _result_metadata(r)
            if impairment and meta.get("impairment") != impairment:
                continue
            steps = meta.get("steps_survived")
            try:
                steps_val: Optional[int] = int(steps) if steps is not None else None
            except (TypeError, ValueError):
                steps_val = None
            out.append(
                InsightRecord(
                    content=_result_text(r),
                    site=str(meta.get("site", "")),
                    persona_id=str(meta.get("persona_id", "")),
                    persona_name=str(meta.get("persona_name", "")),
                    impairment=str(meta.get("impairment", "")),
                    outcome=str(meta.get("outcome", "")),
                    steps_survived=steps_val,
                    score=_result_similarity(r),
                    metadata=meta,
                )
            )
            if len(out) >= limit:
                break
        return out

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        client = getattr(self, "_client", None)
        if client is None:
            return
        for name in ("aclose", "close"):
            fn = getattr(client, name, None)
            if fn is None:
                continue
            try:
                res = fn()
                if hasattr(res, "__await__"):
                    await res
            except Exception:  # noqa: BLE001 - close must never raise
                pass
            return
