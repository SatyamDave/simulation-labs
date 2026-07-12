"""Efficacy CEILING: what if distillation produced a GOOD, actionable playbook?

The heuristic-distilled hints in efficacy.py were non-actionable ("account was
created", "Alex is a power user") and yielded no step reduction. This measures the
ceiling: inject an oracle playbook — the kind an LLM failure-trace distiller SHOULD
produce, grounded in the hostile form's real traps (cookie wall, decoy CTA, promo
field revealed on scroll) — and compare to the OFF baseline from efficacy.py.

Usage: .venv/bin/python bench/efficacy_oracle.py <persona_id> <n> <output_suffix>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import efficacy  # sibling module: reuses TARGET/TASK/_one_run/_instrument/_predicate
from efficacy import _REPO, TARGET, TASK, _one_run

from ghostpanel.engine.holo_client import LiveHoloClient
from ghostpanel.engine.personas import load_personas
from ghostpanel.memory import MODE_SITE_HINTS, create_memory_store

# A grounded, actionable playbook — what a good distiller extracts from failures.
ORACLE_HINTS = [
    "Close the cookie pop-up first by clicking 'Accept all' — it blocks every other click until dismissed.",
    "Type an email address into the Email field.",
    "Scroll down: a required 'Promo code' field only appears after you scroll. Fill it with any value.",
    "To submit, click the plain grey 'Create account' button at the bottom. Do NOT click the blue 'Explore plans' button — it is a decoy that does nothing.",
]


async def main():
    persona_id = sys.argv[1] if len(sys.argv) > 1 else "power-user"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    persona = load_personas([persona_id])[0]
    store = create_memory_store(api_key=os.environ["SUPERMEMORY_API_KEY"], default_mode=MODE_SITE_HINTS)
    holo, _lim = LiveHoloClient.shared(
        api_key=os.environ["HAI_API_KEY"],
        base_url=os.environ.get("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
        model=os.environ.get("HAI_MODEL", "holo3-1-35b-a3b"),
        rpm=float(os.environ.get("HAI_RPM", "5")),
    )

    from playwright.async_api import async_playwright

    runs = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for i in range(n):
            print(f"[oracle {i+1}/{n}] running...", flush=True)
            m, _r = await _one_run(
                browser, holo, persona, store, MODE_SITE_HINTS,
                f"bench-oracle-{i}", override_hints=ORACLE_HINTS,
            )
            m["mode"] = "oracle"
            runs.append(m)
            print(f"  -> outcome={m['outcome']} steps={m['steps']} tokens={m['total_tokens']}", flush=True)
        await browser.close()
    await store.aclose()

    n_ = len(runs)
    oracle = {
        "n": n_,
        "success_rate": sum(r["success"] for r in runs) / n_,
        "mean_steps": sum(r["steps"] for r in runs) / n_,
        "mean_total_tokens": sum(r["total_tokens"] for r in runs) / n_,
        "mean_wall_s": sum(r["wall_s"] for r in runs) / n_,
    }
    # Compare against the OFF baseline recorded by efficacy.py.
    base_path = _REPO / "bench" / "results" / f"efficacy_{persona_id}.json"
    off = json.loads(base_path.read_text())["summary"]["off"] if base_path.exists() else {}
    summary = {"persona": persona_id, "hints": ORACLE_HINTS, "off_baseline": off, "oracle": oracle}
    if off and off.get("mean_steps"):
        summary["step_reduction_pct"] = round(100 * (off["mean_steps"] - oracle["mean_steps"]) / off["mean_steps"], 1)
        summary["token_reduction_pct"] = round(100 * (off["mean_total_tokens"] - oracle["mean_total_tokens"]) / off["mean_total_tokens"], 1)
        summary["success_delta"] = round(oracle["success_rate"] - off["success_rate"], 3)

    out = {"summary": summary, "runs": runs}
    dest = _REPO / "bench" / "results" / f"efficacy_oracle_{persona_id}.json"
    dest.write_text(json.dumps(out, indent=2))
    print("\n=== ORACLE SUMMARY ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
