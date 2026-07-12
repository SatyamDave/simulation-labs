"""B — Live small-swarm survival + impairment cost + trap attribution (LIVE Holo).

Runs a small, budget-bounded swarm of REAL personas end-to-end on the hostile
form with the real Holo model, then quantifies the product's core output:

* survival: outcome + steps-survived per persona
* impairment cost: completion / progress delta vs the unperturbed baseline
* trap attribution: map each persona's failure pixel to the nearest dark-pattern
  trap on the page (decoy button, cookie wall, hidden promo field, ...)

This is the "it's real" proof behind the offline/analytic numbers. Because the
free Holo tier is 5 RPM (server-side, shared), we cap steps per persona
(BENCH_MAX_STEPS, default 8) and run a 3-persona swarm sequentially.

Complements (does not duplicate) ``ghostpanel.benchmarks`` (the swarm-quality /
runner-perf harness): different responsibility — this measures completion
INTEGRITY (a #ok-verified submit vs an ANSWER self-declaration) and maps the
failure pixel to a dark-pattern trap, neither of which that harness reports.

Run:  python -m benchmarks.b_b_survival
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from ghostpanel.engine.holo_client import LiveHoloClient
from ghostpanel.engine.persona_agent import HoloPersonaAgent
from ghostpanel.report.builder import SurvivalReportBuilder
from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.runner.testing import CollectingEventSink
from ghostpanel_contracts import PersonaOutcome

from benchmarks import common as c

SWARM = os.environ.get("BENCH_SWARM", "power-user,low-vision,grandma-72").split(",")
MAX_STEPS = int(os.environ.get("BENCH_MAX_STEPS", "8"))
TASK = "Create an account (sign up) on this page."


async def _ok_visible(page) -> bool:
    """Ground-truth success predicate for the hostile form: the #ok banner shows
    only after a valid submit (email + promo filled, real grey button clicked)."""
    try:
        return await page.locator("#ok").is_visible()
    except Exception:
        return False


async def _trap_boxes():
    """Nearest-trap ground truth: capture every dark-pattern target across the
    two page states, return {trap_label: BBox}."""
    from playwright.async_api import async_playwright

    traps = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(c.hostile_form_url(), wait_until="networkidle")
        traps.update(await _boxes(page, {"cookie_wall": "#cookie button"}))
        await page.locator("#cookie button").first.click()
        await page.wait_for_timeout(300)
        # reveal the scroll-gated promo field so it has a box to attribute to
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(300)
        traps.update(
            await _boxes(
                page,
                {
                    "decoy_button": "form button.btn-decoy",
                    "real_submit": "form button.btn-real",
                    "email_field": "#email",
                    "promo_field": "#promo",
                    "legal_text": ".legal",
                },
            )
        )
        await b.close()
    return traps


async def _boxes(page, selectors):
    out = {}
    for label, sel in selectors.items():
        loc = page.locator(sel).first
        try:
            if await loc.count() == 0:
                continue
            bx = await loc.bounding_box()
        except Exception:
            bx = None
        if bx and bx["width"] > 0 and bx["height"] > 0:
            out[label] = c.BBox(bx["x"], bx["y"], bx["width"], bx["height"])
    return out


def _headline(rows, n_verified, n_selfdecl) -> str:
    """Data-driven headline that reflects the actual outcome mix of this run."""
    n = len(rows)
    abandoned = [r for r in rows if not r["completed"]]
    parts = [
        f"Live on the hostile signup ({n} personas, real Holo): "
        f"{n_verified}/{n} completed and verified by the #ok banner"
    ]
    if n_selfdecl:
        parts.append(
            f", {n_selfdecl} self-declared 'done' via ANSWER without a real submit "
            "(caught mechanically — the people-pleasing failure, quantified)"
        )
    if abandoned:
        who = abandoned[0]
        where = who["failure_coords"]
        parts.append(
            f"; the most-impaired persona ({who['persona']}, {who['outcome']}) "
            f"ran out of an equal step budget at pixel {tuple(where) if where else None} "
            "— impairment inflates steps-to-complete past the limit"
        )
    return "".join(parts) + "."


def _attribute(coords, traps):
    """Nearest trap to a failure pixel (or 'elsewhere' if far from all)."""
    if not coords:
        return "none", None
    x, y = coords
    best, best_d = "elsewhere", 1e9
    for label, bb in traps.items():
        d = bb.dist_to_center(x, y)
        if d < best_d:
            best, best_d = label, d
    return best, round(best_d, 1)


async def run():
    c.load_env()
    api_key = os.environ["HAI_API_KEY"]
    base_url = os.environ.get("HAI_BASE_URL", "https://api.hcompany.ai/v1/")
    model = os.environ.get("HAI_MODEL", "holo3-1-35b-a3b")
    rpm = float(os.environ.get("HAI_RPM", "5"))

    # ONE shared client/limiter across the whole swarm (server-side 5 RPM).
    holo, _limiter = LiveHoloClient.shared(api_key, base_url, model, rpm=rpm)

    personas = []
    for pid in SWARM:
        p = c.load_persona(pid.strip())
        # cap steps to bound the live budget without changing the impairments
        personas.append(p.model_copy(update={"max_steps": min(p.max_steps, MAX_STEPS)}))

    traps = await _trap_boxes()
    target_url = c.hostile_form_url()

    from playwright.async_api import async_playwright

    results = []
    with tempfile.TemporaryDirectory() as artifact_dir:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            runner = PlaywrightSessionRunner(
                browser, artifact_dir, success_predicate=_ok_visible
            )
            for persona in personas:
                # Bind the goal at construction — the runner does NOT forward its
                # `task` arg to the agent, so an unbound agent runs with an empty task.
                agent = HoloPersonaAgent(persona, holo, task=TASK)
                sink = CollectingEventSink()
                res = await runner.run(
                    persona, agent, target_url, TASK, sink, run_id="bench-B"
                )
                results.append(res)
                print(
                    f"  {persona.id:>16}: {res.outcome.value:<12} "
                    f"steps={len(res.steps):<2} fail@{res.failure_coords} "
                    f"({res.failure_reason})"
                )
            await browser.close()

    report = SurvivalReportBuilder().build(
        "bench-B", target_url, TASK, results, personas
    )

    baseline_id = SWARM[0].strip()
    base = next((r for r in results if r.persona_id == baseline_id), None)

    rows = []
    for r in results:
        trap, dist = _attribute(r.failure_coords, traps)
        completed = r.outcome == PersonaOutcome.SUCCESS
        actions = [s.action.type.value for s in r.steps]
        last_type = actions[-1] if actions else None
        # A SUCCESS whose final action is ANSWER is self-declared (the runner
        # short-circuits on ANSWER without checking the page) — flag it as an
        # UNVERIFIED completion vs a real #ok-predicate completion.
        ended_with_answer = last_type == "answer"
        verified = completed and not ended_with_answer
        rows.append(
            {
                "persona": r.persona_id,
                "outcome": r.outcome.value,
                "completed": completed,
                "verified_by_ok": verified,
                "self_declared": completed and ended_with_answer,
                "steps_survived": len(r.steps),
                "sim_seconds": round(r.duration_s, 1),
                "actions": ",".join(actions),
                "failure_coords": list(r.failure_coords) if r.failure_coords else None,
                "trap_hit": trap,
                "trap_dist_px": dist,
            }
        )

    n_success = sum(1 for r in results if r.outcome == PersonaOutcome.SUCCESS)
    n_verified = sum(1 for row in rows if row["verified_by_ok"])
    n_selfdecl = sum(1 for row in rows if row["self_declared"])
    metrics = {
        "swarm_size": len(results),
        "max_steps_cap": MAX_STEPS,
        "completion_rate": round(report.completion_rate, 3),
        "baseline": baseline_id,
        "baseline_completed": bool(base and base.outcome == PersonaOutcome.SUCCESS),
        "n_success": n_success,
        "n_verified_by_ok": n_verified,
        "n_self_declared_answer": n_selfdecl,
        "n_abandoned": len(results) - n_success,
    }
    headline = _headline(rows, n_verified, n_selfdecl)
    c.Result(
        id="b_survival",
        title="Live survival + trap attribution",
        kind="live",
        headline=headline,
        metrics=metrics,
        table=rows,
        notes=(
            f"Real Holo, HAI_RPM={rpm:g}, steps capped at {MAX_STEPS} to bound live "
            "budget. Success = #ok banner visible (real submit). Trap attribution = "
            "nearest dark-pattern element to the failure pixel."
        ),
    ).write()

    print(f"\nHEADLINE: {headline}")
    print(f"metrics: {metrics}")


if __name__ == "__main__":
    asyncio.run(run())
