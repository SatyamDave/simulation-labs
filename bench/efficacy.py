"""Live efficacy benchmark: does site-memory make the swarm cheaper on a repeat visit?

Protocol (the honest "learn across iterations" story):
  1. Run the persona against the hostile form with memory_mode=off (a first-time
     visitor). Record steps, outcome, and EXACT Holo token usage (from the API's
     usage.prompt_tokens — image included). Seed site memory from the run.
  2. Wait for Supermemory ingestion.
  3. Run the SAME persona+task with memory_mode=site_hints (a returning visitor):
     recalled hints are folded into the task exactly as the orchestrator does.
  4. Compare steps + tokens + outcome, off vs on.

Token usage is captured by wrapping the OpenAI client's create() — the real prompt
(degraded screenshot + action-space + history) is measured, nothing is estimated.

Usage: .venv/bin/python bench/efficacy.py <persona_id> <n_off> <n_on> <wait_s>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

_REPO = Path("/Users/udsy/.superset/worktrees/simulation-labs/memory-improvement")
load_dotenv(_REPO / ".env")

import os  # noqa: E402

from ghostpanel_contracts import PersonaOutcome  # noqa: E402
from ghostpanel.engine.holo_client import LiveHoloClient  # noqa: E402
from ghostpanel.engine.persona_agent import HoloPersonaAgent  # noqa: E402
from ghostpanel.engine.personas import load_personas  # noqa: E402
from ghostpanel.memory import MODE_OFF, MODE_SITE_HINTS, create_memory_store  # noqa: E402
from ghostpanel.report.builder import SurvivalReportBuilder  # noqa: E402
from ghostpanel.runner.session import PlaywrightSessionRunner  # noqa: E402
from ghostpanel.runner.testing import CollectingEventSink  # noqa: E402

TARGET = f"file://{_REPO}/fixtures/hostile_form.html"
TASK = (
    "Create a QuantumLeap account: enter the email demo@ghost.test, choose a "
    "password, accept the terms, and click the button that creates the account."
)


def _instrument(holo: LiveHoloClient) -> list[dict]:
    """Wrap the OpenAI create() so every call's exact token usage is captured."""
    usage: list[dict] = []
    orig = holo._client.chat.completions.create

    async def wrapped(**kwargs):
        resp = await orig(**kwargs)
        u = getattr(resp, "usage", None)
        if u is not None:
            usage.append(
                {
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                }
            )
        return resp

    holo._client.chat.completions.create = wrapped  # type: ignore[assignment]
    return usage


async def _predicate(page) -> bool:  # success = the hidden #ok confirmation shows
    try:
        return await page.locator("#ok").is_visible()
    except Exception:  # noqa: BLE001
        return False


async def _one_run(browser, holo, persona, store, mode, run_id, override_hints=None):
    """Run one session; return metrics dict. Hints are injected exactly like the
    orchestrator's _run_one when mode != off. If ``override_hints`` is given, use
    those verbatim instead of recalling (used for the oracle-playbook ceiling)."""
    usage = _instrument(holo)
    effective_task = TASK
    hints: list[str] = []
    if mode != MODE_OFF:
        if override_hints is not None:
            hints = list(override_hints)
        else:
            hints = await store.recall_hints(
                target_url=TARGET, task=TASK, persona=persona, mode=mode
            )
        if hints:
            lines = "\n".join(f"- {h}" for h in hints)
            effective_task = f"{TASK}\n\nWhat helped previous visitors complete this here:\n{lines}"

    agent = HoloPersonaAgent(persona, holo, task=effective_task)
    runner = PlaywrightSessionRunner(browser, _REPO / "artifacts" / "bench", success_predicate=_predicate)
    sink = CollectingEventSink()
    t0 = time.monotonic()
    result = await runner.run(persona, agent, TARGET, TASK, sink, run_id)
    wall = time.monotonic() - t0

    prompt_tokens = sum(u["prompt_tokens"] or 0 for u in usage)
    completion_tokens = sum(u["completion_tokens"] or 0 for u in usage)
    return {
        "mode": mode,
        "run_id": run_id,
        "outcome": result.outcome.value,
        "success": result.outcome == PersonaOutcome.SUCCESS,
        "steps": len(result.steps),
        "holo_calls": len(usage),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "per_step_prompt_tokens": [u["prompt_tokens"] for u in usage],
        "hints_injected": hints,
        "failure_step": result.failure_step,
        "wall_s": round(wall, 1),
    }, result


async def main():
    persona_id = sys.argv[1] if len(sys.argv) > 1 else "power-user"
    n_off = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    n_on = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    wait_s = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    persona = load_personas([persona_id])[0]
    key = os.environ["SUPERMEMORY_API_KEY"]
    store = create_memory_store(api_key=key, default_mode=MODE_SITE_HINTS)
    # One shared Holo client + rate limiter across the whole benchmark (5 RPM).
    holo, _limiter = LiveHoloClient.shared(
        api_key=os.environ["HAI_API_KEY"],
        base_url=os.environ.get("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
        model=os.environ.get("HAI_MODEL", "holo3-1-35b-a3b"),
        rpm=float(os.environ.get("HAI_RPM", "5")),
    )
    builder = SurvivalReportBuilder()

    from playwright.async_api import async_playwright

    runs = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # --- Phase 1: OFF runs (first-time visitors); seed memory from each ---
        for i in range(n_off):
            print(f"[off {i+1}/{n_off}] running...", flush=True)
            m, result = await _one_run(browser, holo, persona, store, MODE_OFF, f"bench-off-{i}")
            runs.append(m)
            print(f"  -> outcome={m['outcome']} steps={m['steps']} tokens={m['total_tokens']}", flush=True)
            report = builder.build(f"bench-off-{i}", TARGET, TASK, [result], [persona])
            wrote = await store.remember_run(
                run_id=f"bench-off-{i}", target_url=TARGET, task=TASK, report=report, personas=[persona]
            )
            print(f"  -> seeded {wrote} memory records", flush=True)

        # --- wait for async ingestion so the ON runs can recall ---
        print(f"waiting {wait_s}s for ingestion...", flush=True)
        await asyncio.sleep(wait_s)

        # --- Phase 2: ON runs (returning visitors) ---
        for i in range(n_on):
            print(f"[on {i+1}/{n_on}] running...", flush=True)
            m, _result = await _one_run(browser, holo, persona, store, MODE_SITE_HINTS, f"bench-on-{i}")
            runs.append(m)
            print(f"  -> outcome={m['outcome']} steps={m['steps']} tokens={m['total_tokens']} hints={len(m['hints_injected'])}", flush=True)

        await browser.close()

    await store.aclose()

    # --- summarize ---
    def agg(mode):
        rs = [r for r in runs if r["mode"] == mode]
        if not rs:
            return {}
        n = len(rs)
        return {
            "n": n,
            "success_rate": sum(r["success"] for r in rs) / n,
            "mean_steps": sum(r["steps"] for r in rs) / n,
            "mean_prompt_tokens": sum(r["prompt_tokens"] for r in rs) / n,
            "mean_total_tokens": sum(r["total_tokens"] for r in rs) / n,
            "mean_wall_s": sum(r["wall_s"] for r in rs) / n,
        }

    off, on = agg(MODE_OFF), agg(MODE_SITE_HINTS)
    summary = {"persona": persona_id, "target": TARGET, "task": TASK, "off": off, "on": on}
    if off and on and off["mean_total_tokens"]:
        summary["token_reduction_pct"] = round(
            100 * (off["mean_total_tokens"] - on["mean_total_tokens"]) / off["mean_total_tokens"], 1
        )
        summary["step_reduction_pct"] = round(
            100 * (off["mean_steps"] - on["mean_steps"]) / off["mean_steps"], 1
        ) if off["mean_steps"] else None

    out = {"summary": summary, "runs": runs}
    dest = _REPO / "bench" / "results" / f"efficacy_{persona_id}.json"
    dest.write_text(json.dumps(out, indent=2))
    print("\n=== SUMMARY ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"\nwrote {dest}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
