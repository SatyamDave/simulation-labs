"""BENCHMARK 2 - recall quality against the real Supermemory API.

Builds a small labeled set across 4 "sites", each tag `gp:bench:quality:<site>`.
Each site's tag is seeded with 3 relevant playbook hints PLUS 3 distractor hints
that topically belong to OTHER sites (to stress precision within a tag). Then for
~8 labeled queries we compute Precision@3 and MRR, and we verify cross-tag
isolation (querying site A never returns site B's rows).

Matching rule (documented in JSON): ingestion may reword content, so a returned
row counts as the target relevant hint when >=2 of the hint's distinctive
keywords appear (case-insensitive substring) in the row text. Non-target rows
seeded under the same tag (distractors + the other 2 relevant hints) are
"not the target". Precision@3 = (target hits in top 3) but since each query has a
single gold hint, we score it as relevant-in-top-3 (hit@3) averaged, and MRR uses
the rank of the first row matching the gold hint.

Cleans up ALL gp:bench:quality:* data at the end and verifies 0 remain.

Run: .venv/bin/python bench/recall_quality.py
"""
from __future__ import annotations

import asyncio
import json

from _common import RESULTS_DIR, cleanup, new_client, row_metadata, row_text, search_rows

SITES = ["checkout", "banking", "airline", "streaming"]


def tag(site: str) -> str:
    return f"gp:bench:quality:{site}"


# Each site: 3 relevant hints (id -> text, keywords). Distractors are the relevant
# hints of the OTHER sites, injected under this site's tag to test precision.
RELEVANT = {
    "checkout": [
        {"id": "co1", "text": "On the checkout page, dismiss the cookie banner before the Continue button becomes clickable.", "kw": ["cookie", "continue"]},
        {"id": "co2", "text": "The promo-code field on checkout is a decoy that empties the cart when focused.", "kw": ["promo", "decoy", "cart"]},
        {"id": "co3", "text": "The real Place Order button on checkout is below the fold under the shipping summary.", "kw": ["place order", "below the fold"]},
    ],
    "banking": [
        {"id": "bk1", "text": "The banking transfer form requires selecting a payee before the amount field unlocks.", "kw": ["transfer", "payee", "amount"]},
        {"id": "bk2", "text": "Two-factor code for the banking login auto-submits after six digits with no button.", "kw": ["two-factor", "six digits", "banking"]},
        {"id": "bk3", "text": "The banking statement download opens a new tab that most popup blockers kill.", "kw": ["statement", "download", "popup"]},
    ],
    "airline": [
        {"id": "al1", "text": "On the airline seat map, exit-row seats are greyed out until you confirm passenger ages.", "kw": ["seat map", "exit-row", "passenger"]},
        {"id": "al2", "text": "The airline fare calendar loads a month late; click Next twice to reach real prices.", "kw": ["fare calendar", "next", "prices"]},
        {"id": "al3", "text": "Baggage add-ons on the airline site only appear after you select a return flight.", "kw": ["baggage", "return flight"]},
    ],
    "streaming": [
        {"id": "st1", "text": "The streaming signup hides the free plan behind a small 'Maybe later' link.", "kw": ["free plan", "maybe later"]},
        {"id": "st2", "text": "Streaming profile creation caps names at ten characters and truncates silently.", "kw": ["profile", "ten characters", "truncate"]},
        {"id": "st3", "text": "The streaming cancel button is inside Account, then Membership, then a red text link.", "kw": ["cancel", "membership", "red text link"]},
    ],
}

# 8 labeled queries: each maps to a (site, gold hint id).
QUERIES = [
    {"q": "how do I make the continue button work on checkout", "site": "checkout", "gold": "co1"},
    {"q": "is the promo code box on checkout real or a trap", "site": "checkout", "gold": "co2"},
    {"q": "where is the place order button", "site": "checkout", "gold": "co3"},
    {"q": "why is the amount field locked on the transfer form", "site": "banking", "gold": "bk1"},
    {"q": "does the banking 2fa need a submit button", "site": "banking", "gold": "bk2"},
    {"q": "how to pick an exit row seat on the airline", "site": "airline", "gold": "al1"},
    {"q": "the fare calendar shows wrong prices", "site": "airline", "gold": "al2"},
    {"q": "where is the cancel button on the streaming service", "site": "streaming", "gold": "st3"},
]


def matches_hint(text: str, keywords: list[str]) -> bool:
    """Relevance match: >=2 distinctive keywords present (or all, if a hint has <2)."""
    t = text.lower()
    hits = sum(1 for k in keywords if k.lower() in t)
    need = min(2, len(keywords))
    return hits >= need


async def main():
    client = new_client()
    tags = [tag(s) for s in SITES]
    out: dict = {
        "benchmark": "recall_quality",
        "matching_rule": "a returned row is the gold hint if >=2 of the hint's distinctive keywords appear as case-insensitive substrings; precision@3 = gold row present in top-3 (hit@3); MRR uses rank of first gold-matching row.",
        "sites": SITES,
    }
    try:
        # ---- seed: each site tag gets its 3 relevant + 3 distractors from other sites ----
        print("[quality] seeding 4 sites x (3 relevant + 3 distractors)...", flush=True)
        seeded_counts = {}
        for site in SITES:
            n = 0
            for h in RELEVANT[site]:
                await client.documents.add(
                    content=h["text"], container_tags=[tag(site)],
                    metadata={"hint_id": h["id"], "role": "relevant", "site": site}, dreaming="instant",
                )
                n += 1
            # distractors: pull one relevant hint from each OTHER site (3 total)
            for other in SITES:
                if other == site:
                    continue
                d = RELEVANT[other][0]
                await client.documents.add(
                    content=d["text"], container_tags=[tag(site)],
                    metadata={"hint_id": d["id"], "role": "distractor", "site": site, "from_site": other}, dreaming="instant",
                )
                n += 1
            seeded_counts[site] = n
        out["seeded_counts"] = seeded_counts

        # ---- wait for ingestion ----
        print("[quality] waiting 30s for ingestion...", flush=True)
        await asyncio.sleep(30)

        # ---- per-query precision@3 + MRR ----
        gold_kw = {h["id"]: h["kw"] for site in SITES for h in RELEVANT[site]}
        print("[quality] scoring 8 labeled queries...", flush=True)
        per_query = []
        for spec in QUERIES:
            rows = await search_rows(client, q=spec["q"], container_tag=tag(spec["site"]), limit=10, rerank=True, threshold=0.0)
            texts = [row_text(r) for r in rows]
            kw = gold_kw[spec["gold"]]
            ranks = [i + 1 for i, t in enumerate(texts) if matches_hint(t, kw)]
            first_rank = ranks[0] if ranks else None
            hit_at_3 = 1 if (first_rank is not None and first_rank <= 3) else 0
            rr = (1.0 / first_rank) if first_rank else 0.0
            per_query.append({
                "q": spec["q"], "site": spec["site"], "gold": spec["gold"],
                "n_rows": len(rows), "first_gold_rank": first_rank,
                "precision_at_3": hit_at_3, "reciprocal_rank": round(rr, 3),
                "top3_texts": [t[:120] for t in texts[:3]],
            })
            print(f"  {spec['gold']}: rank={first_rank} p@3={hit_at_3} rr={round(rr,3)}", flush=True)
        out["per_query"] = per_query
        n = len(per_query)
        out["aggregate"] = {
            "n_queries": n,
            "precision_at_3": round(sum(p["precision_at_3"] for p in per_query) / n, 3),
            "mrr": round(sum(p["reciprocal_rank"] for p in per_query) / n, 3),
        }
        print(f"  P@3={out['aggregate']['precision_at_3']} MRR={out['aggregate']['mrr']}", flush=True)

        # ---- cross-tag isolation: query site A's tag, ensure no row's metadata.site != A ----
        print("[quality] cross-tag isolation check...", flush=True)
        leaks = []
        checks = 0
        for spec in QUERIES:
            for site in SITES:
                if site == spec["site"]:
                    continue
                # query with a query whose gold lives in spec['site'], but against `site`'s tag
                rows = await search_rows(client, q=spec["q"], container_tag=tag(site), limit=10, rerank=True, threshold=0.0)
                checks += 1
                for r in rows:
                    md = row_metadata(r)
                    row_site = md.get("site")
                    # every row under tag(site) must have been seeded with site==site
                    if row_site is not None and row_site != site:
                        leaks.append({"query_site": spec["site"], "queried_tag": site, "row_site": row_site, "text": row_text(r)[:100]})
        out["isolation"] = {
            "checks": checks,
            "leaks": leaks,
            "pass": len(leaks) == 0,
            "note": "Each row is tagged with metadata.site == the tag it was seeded under. A leak = a row surfaced under a tag it was never written to. Container tags are isolated namespaces, so 0 leaks is expected.",
        }
        print(f"  isolation checks={checks} leaks={len(leaks)} pass={out['isolation']['pass']}", flush=True)

    finally:
        print("[quality] cleaning up...", flush=True)
        out["cleanup"] = await cleanup(client, tags)
        await client.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / "recall_quality.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"[quality] cleanup residual={out['cleanup']['residual']}", flush=True)
    print(f"[quality] wrote {dest}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
