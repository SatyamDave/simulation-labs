"""BENCHMARK 3 - scaling against the real Supermemory API.

Measures how recall holds as the insight base grows. Seeds the tag
`gp:bench:scale` in increments to sizes ~[25, 100, 250], each record a realistic
insight-style sentence carrying a metadata `impairment` in
{blur, tremor, cvd, low_literacy, none}. A distinctive NEEDLE insight is planted
first. After each size increment we wait for ingestion, then:
  - RECALL latency at that store size (~15 queries -> p50/p95 ms)
  - NEEDLE RETENTION: query for the needle; record its top-5 rank + similarity
  - impairment-filtered recall: search then filter by metadata.impairment in Python

Writes ~250 records; cleans up ALL gp:bench:scale at the end and verifies 0 remain.

Run: .venv/bin/python bench/scaling.py
"""
from __future__ import annotations

import asyncio
import json
import time

from _common import (
    RESULTS_DIR,
    cleanup,
    new_client,
    pct,
    row_metadata,
    row_text,
    search_rows,
    stats_ms,
    wait_until_searchable,
)

TAG = "gp:bench:scale"
IMPAIRMENTS = ["blur", "tremor", "cvd", "low_literacy", "none"]

NEEDLE_TEXT = (
    "On the Zephyr Aurora insurance portal, the platinum-tier renewal toggle is a "
    "hidden lavender switch in the top-right that only appears after hovering the "
    "policy number for two seconds."
)
NEEDLE_QUERY = "Zephyr Aurora insurance platinum renewal lavender toggle policy number"
NEEDLE_MARKERS = ["zephyr aurora", "lavender", "platinum"]

# Building blocks to synthesize varied, realistic insight sentences.
_SITES = ["checkout", "onboarding wizard", "seat map", "banking dashboard", "signup flow",
          "settings page", "cart", "search results", "profile editor", "booking calendar"]
_FRICTIONS = [
    "the primary CTA sits below the fold and is missed on first pass",
    "the cookie banner intercepts the first two clicks",
    "low-contrast placeholder text reads as a filled field",
    "the submit button stays disabled until an off-screen field is touched",
    "a modal overlay steals focus right after load",
    "the required checkbox is styled as plain text and overlooked",
    "error messages render below the viewport and look like a no-op",
    "the stepper drops rapid clicks and undercounts quantity",
    "autocomplete hijacks the Enter key and submits early",
    "the real action link is disguised as secondary grey text",
    "tab order skips the password field entirely",
    "the icon-only button has no label and is ignored",
]


def _sentence(i: int) -> tuple[str, str]:
    site = _SITES[i % len(_SITES)]
    fric = _FRICTIONS[(i * 7) % len(_FRICTIONS)]
    imp = IMPAIRMENTS[i % len(IMPAIRMENTS)]
    prefix = {
        "blur": "Low-vision (blur) users report that",
        "tremor": "Tremor users repeatedly overshoot because",
        "cvd": "Colour-blind (CVD) users cannot tell that",
        "low_literacy": "Low-literacy users are confused when",
        "none": "Even unimpaired users find that",
    }[imp]
    text = f"On the {site}, {prefix} {fric} (insight #{i})."
    return text, imp


async def _seed(client, start: int, end: int):
    """Seed records with global index in [start, end)."""
    for i in range(start, end):
        text, imp = _sentence(i)
        await client.documents.add(
            content=text, container_tags=[TAG],
            metadata={"idx": i, "impairment": imp, "kind": "insight"}, dreaming="instant",
        )


async def _measure(client, size_label: int) -> dict:
    # ~15 recall queries at this store size
    queries = [f"On the {s}, {f[:30]}" for s in _SITES[:8] for f in _FRICTIONS[:2]][:15]
    lat_ms = []
    for q in queries:
        t0 = time.perf_counter()
        await search_rows(client, q=q, container_tag=TAG, limit=10, rerank=True, threshold=0.0)
        lat_ms.append((time.perf_counter() - t0) * 1000)
    lat = stats_ms(lat_ms)

    # needle retention: rank + similarity in top-5
    rows = await search_rows(client, q=NEEDLE_QUERY, container_tag=TAG, limit=5, rerank=True, threshold=0.0)
    needle_rank, needle_sim = None, None
    for idx, r in enumerate(rows):
        if any(m in row_text(r).lower() for m in NEEDLE_MARKERS):
            needle_rank = idx + 1
            from _common import row_score
            needle_sim = row_score(r)
            break

    # impairment-filtered recall: search broadly, filter to blur in Python
    t0 = time.perf_counter()
    frows = await search_rows(client, q="users struggle with the button and form", container_tag=TAG, limit=25, rerank=True, threshold=0.0)
    filt_ms = (time.perf_counter() - t0) * 1000
    blur_rows = [r for r in frows if row_metadata(r).get("impairment") == "blur"]

    return {
        "size": size_label,
        "recall_p50_ms": lat.get("p50"),
        "recall_p95_ms": lat.get("p95"),
        "recall_mean_ms": lat.get("mean"),
        "needle_rank_top5": needle_rank,
        "needle_similarity": needle_sim,
        "impairment_filter": {
            "query_latency_ms": round(filt_ms, 1),
            "rows_returned": len(frows),
            "blur_rows_after_filter": len(blur_rows),
        },
    }


async def main():
    client = new_client()
    out: dict = {"benchmark": "scaling", "tag": TAG, "needle": NEEDLE_TEXT, "sizes": []}
    targets = [25, 100, 250]
    try:
        # plant the needle first (global index -1 handled specially)
        print("[scaling] planting needle...", flush=True)
        await client.documents.add(
            content=NEEDLE_TEXT, container_tags=[TAG],
            metadata={"idx": -1, "impairment": "blur", "kind": "needle"}, dreaming="instant",
        )
        seeded = 1  # needle counts toward the store size
        for target in targets:
            add_to = target
            print(f"[scaling] growing store to ~{target} (currently {seeded})...", flush=True)
            await _seed(client, seeded - 1, add_to - 1)  # fill remaining non-needle slots
            seeded = target
            print(f"[scaling] waiting 30s for ingestion at size {target}...", flush=True)
            await asyncio.sleep(30)
            # ensure needle is searchable before measuring (first size only, cheap safety)
            if target == targets[0]:
                lag = await wait_until_searchable(
                    client, container_tag=TAG, q=NEEDLE_QUERY, needle_substrings=NEEDLE_MARKERS, timeout=40, interval=2,
                )
                print(f"  needle searchable after {lag}s", flush=True)
            m = await _measure(client, target)
            out["sizes"].append(m)
            print(f"  size={target} p50={m['recall_p50_ms']}ms p95={m['recall_p95_ms']}ms needle_rank={m['needle_rank_top5']} sim={m['needle_similarity']}", flush=True)

        # scaling table (compact)
        out["table"] = [
            {"size": m["size"], "recall_p50_ms": m["recall_p50_ms"], "recall_p95_ms": m["recall_p95_ms"],
             "needle_rank": m["needle_rank_top5"], "needle_similarity": m["needle_similarity"]}
            for m in out["sizes"]
        ]

    finally:
        print("[scaling] cleaning up (delete ~250 records)...", flush=True)
        out["cleanup"] = await cleanup(client, [TAG])
        await client.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / "scaling.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"[scaling] cleanup residual={out['cleanup']['residual']}", flush=True)
    print(f"[scaling] wrote {dest}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
