"""BENCHMARK 1 - latency against the real Supermemory API.

Measures, all under the dedicated tag `gp:bench:latency`:
  - RECALL latency (rerank=True): ~30 varied queries -> p50/p90/p95/p99/min/max/mean ms
  - RECALL latency rerank=False vs True (does rerank cost latency?)
  - WRITE latency: ~20 documents.add calls -> p50/p95/mean ms (API-accept time only)
  - INGESTION LAG: write a uniquely-tagged doc, poll until searchable; repeat 3-5x.

Cleans up ALL gp:bench:latency* data at the end and verifies 0 remain.

Run: .venv/bin/python bench/latency.py
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from _common import (
    RESULTS_DIR,
    cleanup,
    new_client,
    search_rows,
    stats_ms,
    wait_until_searchable,
)

TAG = "gp:bench:latency"
INGEST_TAG = "gp:bench:latency:ingest"  # separate tag for ingestion-lag probes
ALL_TAGS = [TAG, INGEST_TAG]

# ~20 realistic site-playbook-style hint sentences to pre-seed.
SEED_HINTS = [
    "Dismiss the cookie consent banner before interacting with the checkout form.",
    "The real Continue button sits below the fold; scroll down past the hero image.",
    "The promo-code field is a decoy that resets the cart when focused.",
    "Email verification link lands in spam for gmail addresses on this site.",
    "The password field silently truncates input over 20 characters.",
    "Terms checkbox is styled as a link and easy to miss on mobile widths.",
    "The account-creation button is labeled 'Get started', not 'Sign up'.",
    "A modal overlay steals the first click after the page loads; click twice.",
    "The quantity stepper needs a full second between clicks or it drops events.",
    "Shipping options only appear after a valid ZIP code is entered.",
    "The search box autocompletes and hijacks Enter; press Escape first.",
    "Card number field rejects spaces; type the digits with no separators.",
    "The 'Apply' button for the coupon is disabled until the field loses focus.",
    "Guest checkout is hidden behind a small 'Continue without account' text link.",
    "The date picker opens off-screen on narrow viewports; use keyboard arrows.",
    "Two-factor code input auto-submits after 6 digits, no button press needed.",
    "The newsletter opt-in is pre-checked; uncheck it before submitting.",
    "Error messages render below the fold, so a failed submit looks like a no-op.",
    "The logo click returns home and wipes the cart without confirmation.",
    "Session expires after 3 minutes idle; the form clears silently on resubmit.",
]

# ~30 varied recall queries touching the seeded topics.
QUERIES = [
    "how do I get past the cookie banner",
    "where is the continue button",
    "is the promo code field real",
    "why did my verification email not arrive",
    "password length limit",
    "how to accept the terms",
    "what is the sign up button called",
    "modal blocks my first click",
    "quantity buttons dropping clicks",
    "when do shipping options show",
    "search box eats my enter key",
    "card number format",
    "coupon apply button disabled",
    "checkout without an account",
    "date picker off screen",
    "2fa auto submit",
    "newsletter checkbox pre-checked",
    "where do errors appear",
    "clicking the logo cleared my cart",
    "session timeout clears the form",
    "cookie consent overlay",
    "button below the fold",
    "decoy input field checkout",
    "spam folder email link",
    "truncated password input",
    "terms checkbox hidden",
    "get started button account",
    "overlay steals click on load",
    "stepper needs delay between clicks",
    "zip code required for shipping",
]


async def main():
    client = new_client()
    out: dict = {"benchmark": "latency", "tag": TAG}
    try:
        # ---- WRITE latency (also serves as the seed) ----
        print(f"[latency] seeding {len(SEED_HINTS)} records, timing writes...", flush=True)
        write_ms = []
        for i, hint in enumerate(SEED_HINTS):
            t0 = time.perf_counter()
            await client.documents.add(
                content=hint,
                container_tags=[TAG],
                metadata={"idx": i, "kind": "playbook_hint"},
                dreaming="instant",
            )
            write_ms.append((time.perf_counter() - t0) * 1000)
        out["write_latency_ms"] = stats_ms(write_ms)
        out["write_latency_ms"]["raw"] = [round(x, 1) for x in write_ms]
        print(f"  write p50={out['write_latency_ms']['p50']}ms p95={out['write_latency_ms']['p95']}ms", flush=True)

        # ---- wait for ingestion so recall has something to find ----
        print("[latency] waiting 25s for ingestion...", flush=True)
        await asyncio.sleep(25)
        # confirm at least some seeds are searchable before timing recall
        probe = await search_rows(client, q="cookie banner checkout", container_tag=TAG, limit=5, rerank=True, threshold=0.0)
        print(f"  probe found {len(probe)} rows after wait", flush=True)

        # ---- RECALL latency rerank=True (~30 queries) ----
        print("[latency] recall latency rerank=True (30 queries)...", flush=True)
        rec_true_ms, rec_true_rows = [], []
        for q in QUERIES:
            t0 = time.perf_counter()
            rows = await search_rows(client, q=q, container_tag=TAG, limit=10, rerank=True, threshold=0.0)
            rec_true_ms.append((time.perf_counter() - t0) * 1000)
            rec_true_rows.append(len(rows))
        out["recall_latency_rerank_true_ms"] = stats_ms(rec_true_ms)
        out["recall_latency_rerank_true_ms"]["raw"] = [round(x, 1) for x in rec_true_ms]
        out["recall_mean_rows_returned"] = round(sum(rec_true_rows) / len(rec_true_rows), 2)
        print(f"  rerank=True p50={out['recall_latency_rerank_true_ms']['p50']}ms p95={out['recall_latency_rerank_true_ms']['p95']}ms", flush=True)

        # ---- RECALL latency rerank=False (same queries) ----
        print("[latency] recall latency rerank=False (30 queries)...", flush=True)
        rec_false_ms = []
        for q in QUERIES:
            t0 = time.perf_counter()
            await search_rows(client, q=q, container_tag=TAG, limit=10, rerank=False, threshold=0.0)
            rec_false_ms.append((time.perf_counter() - t0) * 1000)
        out["recall_latency_rerank_false_ms"] = stats_ms(rec_false_ms)
        out["recall_latency_rerank_false_ms"]["raw"] = [round(x, 1) for x in rec_false_ms]
        a = out["recall_latency_rerank_false_ms"]["p50"]
        b = out["recall_latency_rerank_true_ms"]["p50"]
        out["rerank_p50_overhead_ms"] = round(b - a, 1)
        print(f"  rerank=False p50={a}ms | rerank overhead at p50 = {out['rerank_p50_overhead_ms']}ms", flush=True)

        # ---- INGESTION LAG: 4 probes, unique doc -> poll until searchable ----
        print("[latency] ingestion lag (4 probes, poll every 2s, 60s timeout)...", flush=True)
        lags = []
        for i in range(4):
            token = uuid.uuid4().hex[:10]
            content = f"Ingestion lag probe {token}: the Zephyr wizard step {i} is a distinctive marker sentence."
            await client.documents.add(
                content=content,
                container_tags=[INGEST_TAG],
                metadata={"probe": i, "token": token},
                dreaming="instant",
            )
            lag = await wait_until_searchable(
                client, container_tag=INGEST_TAG, q=f"ingestion lag probe {token} distinctive marker",
                needle_substrings=[token, "distinctive marker"], timeout=60, interval=2,
            )
            lags.append(lag)
            print(f"  probe {i}: time-to-searchable = {lag}s", flush=True)
        searchable = [x for x in lags if x is not None]
        out["ingestion_lag_s"] = {
            "raw": lags,
            "n_appeared": len(searchable),
            "n_timeout": len([x for x in lags if x is None]),
            "min": round(min(searchable), 2) if searchable else None,
            "median": round(sorted(searchable)[len(searchable) // 2], 2) if searchable else None,
            "max": round(max(searchable), 2) if searchable else None,
            "mean": round(sum(searchable) / len(searchable), 2) if searchable else None,
        }
        print(f"  ingestion lag median={out['ingestion_lag_s']['median']}s", flush=True)

    finally:
        print("[latency] cleaning up...", flush=True)
        out["cleanup"] = await cleanup(client, ALL_TAGS)
        await client.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / "latency.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"[latency] cleanup residual={out['cleanup']['residual']}", flush=True)
    print(f"[latency] wrote {dest}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
