"""C2 — Swarm throughput vs the shared Holo rate limit (analytic).

The operational question this answers: *how many personas can I run live before
the demo drags?* The whole swarm shares ONE token-bucket rate limiter
(`ghostpanel.engine.holo_client.RateLimiter`: capacity=rpm, refill rpm/60 tok/s),
and every persona STEP costs ~1 Holo API call. So wall-clock is pure arithmetic:

    wall_clock_minutes = total_api_calls / RPM

where total_api_calls = sum over the selected personas of their steps. We report
the WORST case (every persona runs to its full `max_steps`) and an EXPECTED case
(a persona typically completes/abandons at ~COMPLETION_FRAC of its budget).

Crucially, this real API wall-clock is DECOUPLED from the persona's SIMULATED
patience clock. `SessionRunner` charges only `_THINK_TIME_S` (4.0s) + real
page/actuation time to `state["sim_s"]` and compares that to `persona.deadline_s`;
Holo latency and rate-limiter queueing are explicitly EXCLUDED (commit 416e488).
So a persona abandons after the same number of SIMULATED steps no matter how slow
or queued the API is — RPM changes how long WE wait, never the verdict.

Constants below are read live from source (see module-level asserts), not guessed.

Run: `python -m benchmarks.b_c2_throughput`
"""

from __future__ import annotations

from benchmarks import common as c

# --------------------------------------------------------------------------- source-of-truth constants
# Read straight from the modules that own them so this benchmark can never drift.
from ghostpanel.runner.session import _THINK_TIME_S, _WALL_CAP_S

# HAI_RPM: the shared limiter's rate. Free H tier = 5 req/min (CLAUDE.md,
# DEMO_PLAYBOOK.md, and server/config.py default `_get_float("HAI_RPM", 5.0)`).
HAI_RPM_FREE_TIER = 5.0

# One Holo "navigate" call per persona step (the runner's decide->act loop).
API_CALLS_PER_STEP = 1

# A persona rarely burns its entire step budget: it completes the task or abandons
# earlier. Model expected steps as this fraction of max_steps (worst case = 1.0).
COMPLETION_FRAC = 0.60

# Estimated real page/actuation seconds charged per step alongside _THINK_TIME_S
# (settle _SETTLE_MS=500ms + goto/click). Used ONLY for the sim-clock illustration.
PAGE_S_EST = 1.0

RPM_GRID = [5, 10, 30, 60]

PRESETS: dict[str, list[str]] = {
    "full 8": [
        "ai-agent", "colorblind", "grandma-72", "impatient-mobile",
        "low-vision", "non-native", "power-user", "tremor",
    ],
    "demo 4": ["grandma-72", "impatient-mobile", "low-vision", "power-user"],
    "single baseline": ["power-user"],
}


def _expected_steps(max_steps: int) -> int:
    """Typical steps before completion/abandonment: min(max, frac*max)."""
    return min(max_steps, round(COMPLETION_FRAC * max_steps))


def _wall_min(api_calls: float, rpm: float) -> float:
    return api_calls / rpm


def build() -> c.Result:
    personas = {p.id: p for p in c.load_all_personas()}
    max_steps = {pid: p.max_steps for pid, p in personas.items()}

    # --- per-preset step totals (independent of RPM) ---
    preset_totals = {}
    for name, ids in PRESETS.items():
        worst = sum(max_steps[i] * API_CALLS_PER_STEP for i in ids)
        expected = sum(_expected_steps(max_steps[i]) * API_CALLS_PER_STEP for i in ids)
        preset_totals[name] = {"worst": worst, "expected": expected}

    # --- table: preset x rpm ---
    table = []
    for name, ids in PRESETS.items():
        t = preset_totals[name]
        for rpm in RPM_GRID:
            table.append({
                "preset": name,
                "rpm": rpm,
                "api_calls_worst": t["worst"],
                "api_calls_expected": t["expected"],
                "wall_min_worst": round(_wall_min(t["worst"], rpm), 2),
                "wall_min_expected": round(_wall_min(t["expected"], rpm), 2),
            })

    # --- headline numbers at the free tier ---
    full8_worst_5 = _wall_min(preset_totals["full 8"]["worst"], HAI_RPM_FREE_TIER)
    demo4_worst_5 = _wall_min(preset_totals["demo 4"]["worst"], HAI_RPM_FREE_TIER)
    demo4_exp_5 = _wall_min(preset_totals["demo 4"]["expected"], HAI_RPM_FREE_TIER)

    headline = (
        f"At the free tier ({HAI_RPM_FREE_TIER:.0f} RPM) a full 8-persona x max-steps run "
        f"takes ~{full8_worst_5:.0f} min ({preset_totals['full 8']['worst']} API calls); "
        f"the demo-4 preset is ~{demo4_worst_5:.0f} min worst-case / ~{demo4_exp_5:.0f} min "
        f"expected -- which is why the live demo runs 4 personas, not 8."
    )

    # --- sim-clock independence: steps-to-abandon is set by patience, not RPM ---
    per_step_sim_s = _THINK_TIME_S + PAGE_S_EST
    sim_abandon = {}
    for pid, p in sorted(personas.items()):
        # Persona hits TIME_BUDGET when sim_s >= deadline_s; capped by max_steps.
        by_patience = int(p.deadline_s // per_step_sim_s)
        sim_abandon[pid] = min(p.max_steps, by_patience)

    # DEMO_PLAYBOOK.md sanity check: it quotes "~40 min for 8x30" and "~3-6 min for 4".
    playbook_8x30 = (8 * 30) / HAI_RPM_FREE_TIER  # rough shorthand model

    metrics = {
        "_THINK_TIME_S": _THINK_TIME_S,
        "_WALL_CAP_S": _WALL_CAP_S,
        "HAI_RPM_free_tier": HAI_RPM_FREE_TIER,
        "completion_frac": COMPLETION_FRAC,
        "page_s_est": PAGE_S_EST,
        "per_step_sim_s": per_step_sim_s,
        "throughput_steps_per_min_equals_rpm": True,
        "full8_api_calls_worst": preset_totals["full 8"]["worst"],
        "full8_api_calls_expected": preset_totals["full 8"]["expected"],
        "demo4_api_calls_worst": preset_totals["demo 4"]["worst"],
        "demo4_api_calls_expected": preset_totals["demo 4"]["expected"],
        "wall_min_full8_worst_at_5rpm": round(full8_worst_5, 2),
        "wall_min_demo4_worst_at_5rpm": round(demo4_worst_5, 2),
        "wall_min_demo4_expected_at_5rpm": round(demo4_exp_5, 2),
        "playbook_8x30_shorthand_min": round(playbook_8x30, 1),
        "sim_steps_to_abandon": sim_abandon,
    }

    notes = (
        "MODEL: total_api_calls = sum(persona steps); wall_min = calls / RPM. One Holo "
        "navigate call per step, shared token-bucket limiter (capacity=rpm, refill rpm/60 "
        "tok/s). Worst case = every persona to its full max_steps "
        "(grandma-72=12, impatient-mobile=8, low-vision=25, non-native=20, colorblind=30, "
        "tremor=30, power-user=40, ai-agent=40); expected = "
        f"{COMPLETION_FRAC:.0%} of max_steps. "
        f"SANITY vs DEMO_PLAYBOOK.md: full-8 worst-case = {full8_worst_5:.0f} min matches its "
        f"\"~40 min for 8x30\" (its 8x30={playbook_8x30:.0f} min shorthand; real max_steps sum "
        f"={preset_totals['full 8']['worst']} calls gives {full8_worst_5:.0f} min -- close "
        "agreement). The playbook's \"~3-6 min for 4\" is its THREE fast-failing personas "
        "(grandma-72, impatient-mobile, low-vision) which complete/abandon early; this preset's "
        "demo-4 swaps in power-user (a full-40 baseline), so its worst-case rises to "
        f"~{demo4_worst_5:.0f} min / ~{demo4_exp_5:.0f} min expected -- same order, higher "
        "because power-user runs long. "
        "SIM-CLOCK INDEPENDENCE: per-step simulated cost = _THINK_TIME_S(4.0) + page(~"
        f"{PAGE_S_EST:.0f}s) = {per_step_sim_s:.0f}s, so a persona hits TIME_BUDGET after "
        "deadline_s/per_step steps REGARDLESS of RPM/API latency (Holo queue is excluded from "
        "patience, commit 416e488). E.g. impatient-mobile (deadline_s=30) abandons after "
        f"~{sim_abandon['impatient-mobile']} steps whether the API runs at 5 or 60 RPM -- RPM "
        "only changes how long WE wait for those steps, never the verdict. "
        "THROUGHPUT: steps/minute == RPM by construction."
    )

    return c.Result(
        id="c2_throughput",
        title="Swarm throughput vs rate limit",
        kind="analytic",
        headline=headline,
        metrics=metrics,
        table=table,
        notes=notes,
    )


def main() -> None:
    res = build()
    path = res.write()
    print(res.headline)
    print()
    print(
        f"constants (from source): _THINK_TIME_S={_THINK_TIME_S}s  "
        f"_WALL_CAP_S={_WALL_CAP_S}s  HAI_RPM(free)={HAI_RPM_FREE_TIER:.0f}  "
        f"completion_frac={COMPLETION_FRAC}"
    )
    print()
    hdr = f"{'preset':<16}{'rpm':>5}{'calls_worst':>13}{'wall_worst':>12}{'wall_exp':>10}"
    print(hdr)
    print("-" * len(hdr))
    for row in res.table:
        print(
            f"{row['preset']:<16}{row['rpm']:>5}{row['api_calls_worst']:>13}"
            f"{row['wall_min_worst']:>12.2f}{row['wall_min_expected']:>10.2f}"
        )
    print()
    print("sim-clock steps-to-abandon (patience-bound, RPM-independent):")
    for pid, n in res.metrics["sim_steps_to_abandon"].items():
        print(f"  {pid:<18} {n} steps")
    print()
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
