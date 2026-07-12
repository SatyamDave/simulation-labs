"""Shared helpers for the Supermemory live benchmarks (bench/*.py).

All benchmarks write ONLY under the dedicated `gp:bench:*` tag namespace and
clean everything up at the end via delete_bulk. This module centralizes the
client factory, result-row extraction, percentile math, and cleanup so the
three scripts stay small and consistent.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path("/Users/udsy/.superset/worktrees/simulation-labs/memory-improvement")
load_dotenv(REPO / ".env")

from supermemory import AsyncSupermemory  # noqa: E402

RESULTS_DIR = REPO / "bench" / "results"
BASE_URL = "https://api.supermemory.ai"


def new_client() -> AsyncSupermemory:
    """Always pass base_url explicitly (a blank env var otherwise breaks it)."""
    return AsyncSupermemory(api_key=os.environ["SUPERMEMORY_API_KEY"], base_url=BASE_URL)


def row_text(row) -> str:
    """Best-effort text of a search result row across memory/chunk/content shapes."""
    for attr in ("memory", "chunk", "content", "text", "summary"):
        v = getattr(row, attr, None)
        if isinstance(v, str) and v.strip():
            return v
    # some rows nest chunks
    chunks = getattr(row, "chunks", None)
    if chunks:
        parts = []
        for c in chunks:
            t = getattr(c, "content", None) or getattr(c, "text", None)
            if isinstance(t, str):
                parts.append(t)
        if parts:
            return " ".join(parts)
    return ""


def row_score(row) -> float | None:
    for attr in ("similarity", "score", "rerank_score"):
        v = getattr(row, attr, None)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def row_metadata(row) -> dict:
    md = getattr(row, "metadata", None)
    if isinstance(md, dict):
        return md
    if md is not None and hasattr(md, "__dict__"):
        return {k: v for k, v in vars(md).items() if not k.startswith("_")}
    return {}


async def search_rows(client, q, container_tag, limit=10, rerank=True, threshold=0.0):
    resp = await client.search.memories(
        q=q, container_tag=container_tag, limit=limit, rerank=rerank, threshold=threshold
    )
    return getattr(resp, "results", []) or []


def pct(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile (p in 0..100). None for empty input."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return xs[int(k)]
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def stats_ms(values: list[float]) -> dict:
    """Summary stats for a list of millisecond timings."""
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": round(min(values), 1),
        "p50": round(pct(values, 50), 1),
        "p90": round(pct(values, 90), 1),
        "p95": round(pct(values, 95), 1),
        "p99": round(pct(values, 99), 1),
        "max": round(max(values), 1),
        "mean": round(sum(values) / len(values), 1),
    }


async def cleanup(client, tags: list[str]) -> dict:
    """Delete every bench tag and verify 0 rows remain by re-searching each tag."""
    deleted = {}
    for t in tags:
        try:
            r = await client.documents.delete_bulk(container_tags=[t])
            deleted[t] = int(getattr(r, "deleted_count", 0) or 0)
        except Exception as e:  # noqa: BLE001
            deleted[t] = f"error: {e}"
    # verify empty
    residual = {}
    for t in tags:
        try:
            rows = await search_rows(client, q="*", container_tag=t, limit=50, rerank=False, threshold=0.0)
            residual[t] = len(rows)
        except Exception as e:  # noqa: BLE001
            residual[t] = f"error: {e}"
    return {"deleted": deleted, "residual": residual}


async def wait_until_searchable(client, container_tag, q, needle_substrings, timeout=60, interval=2):
    """Poll search until a row matching any needle substring appears. Returns seconds or None."""
    t0 = time.perf_counter()
    needles = [n.lower() for n in needle_substrings]
    while time.perf_counter() - t0 < timeout:
        rows = await search_rows(client, q=q, container_tag=container_tag, limit=10, rerank=False, threshold=0.0)
        for row in rows:
            txt = row_text(row).lower()
            if any(n in txt for n in needles):
                return round(time.perf_counter() - t0, 2)
        await __import__("asyncio").sleep(interval)
    return None
