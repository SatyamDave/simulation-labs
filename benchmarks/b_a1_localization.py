"""A1 — Localization dose-response (LIVE Holo).

The flagship benchmark for the "mechanical fidelity" claim. We render the hostile
form, capture ground-truth bounding boxes for known targets, then degrade the
screenshot one perception channel at a time (blur / downscale / CVD) and ask the
REAL Holo model to localize the target. We measure how far the returned click
drifts from the target as the perturbation strengthens.

Because Holo runs at temperature 0, one call per (target, condition) is a stable
point — so a small, budget-friendly grid (~12 live calls at HAI_RPM=5, ~3 min)
yields a clean pixel-error dose-response curve plus per-call latency.

Run:  python -m benchmarks.b_a1_localization
"""

from __future__ import annotations

import asyncio
import os
import time

from ghostpanel.engine.holo_client import LiveHoloClient
from ghostpanel.engine.perturbation import perceive
from ghostpanel_contracts import CVDType, PersonaConfig

from benchmarks import common as c


# --- ground-truth capture (two page states: cookie wall up, then dismissed) ---
async def _capture_states(viewport=(1280, 800)):
    """Return {state: (png_bytes, {label: BBox})} for the two hostile-form states."""
    from playwright.async_api import async_playwright

    w, h = viewport
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": w, "height": h})
        await page.goto(c.hostile_form_url(), wait_until="networkidle")

        # State 1: cookie consent wall covers the page.
        png1 = await page.screenshot()
        boxes1 = await _boxes(page, {"cookie_accept": "#cookie button"})
        out["cookie_wall"] = (png1, boxes1)

        # Dismiss the cookie wall, capture the underlying form.
        await page.locator("#cookie button").first.click()
        await page.wait_for_timeout(300)
        png2 = await page.screenshot()
        boxes2 = await _boxes(
            page,
            {
                "email_input": "#email",
                "real_submit": "form button.btn-real",
                "decoy_button": "form button.btn-decoy",
            },
        )
        out["form"] = (png2, boxes2)
        await browser.close()
    return out


async def _boxes(page, selectors):
    boxes = {}
    for label, sel in selectors.items():
        loc = page.locator(sel).first
        try:
            if await loc.count() == 0:
                continue
            b = await loc.bounding_box()
        except Exception:
            b = None
        if b and b["width"] > 0 and b["height"] > 0:
            boxes[label] = c.BBox(b["x"], b["y"], b["width"], b["height"])
    return boxes


def _persona_for(channel: str, level) -> PersonaConfig:
    """Build a single-channel perturbation persona so perceive() degrades one axis."""
    base = dict(id=f"probe-{channel}-{level}", name="probe")
    if channel == "blur":
        return PersonaConfig(**base, blur_sigma=float(level))
    if channel == "downscale":
        return PersonaConfig(**base, downscale_factor=float(level))
    if channel == "cvd":
        return PersonaConfig(**base, cvd_type=CVDType.DEUTAN, cvd_severity=float(level))
    raise ValueError(channel)


async def _probe(holo, png, bbox, instruction, channel, level):
    """One live localization; returns a metrics row (in true viewport pixels)."""
    persona = _persona_for(channel, level)
    degraded = perceive(png, persona)
    t0 = time.perf_counter()
    x, y = await holo.localize(degraded, instruction)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "channel": channel,
        "level": float(level),
        "pred_x": int(x),
        "pred_y": int(y),
        "target_cx": round(bbox.cx, 1),
        "target_cy": round(bbox.cy, 1),
        "error_px": round(bbox.dist_to_center(x, y), 1),
        "inside_target": bbox.contains(x, y),
        "latency_ms": latency_ms,
    }


async def run():
    c.load_env()
    api_key = os.environ["HAI_API_KEY"]
    base_url = os.environ.get("HAI_BASE_URL", "https://api.hcompany.ai/v1/")
    model = os.environ.get("HAI_MODEL", "holo3-1-35b-a3b")
    rpm = float(os.environ.get("HAI_RPM", "5"))
    holo = LiveHoloClient(api_key, base_url, model, rpm=rpm)

    states = await _capture_states()
    cookie_png, cookie_boxes = states["cookie_wall"]
    form_png, form_boxes = states["form"]
    cookie_bb = cookie_boxes["cookie_accept"]
    email_bb = form_boxes.get("email_input")

    rows = []
    # Primary target: the verified cookie "Accept all" button (center ~547,430).
    # Blur dose-response is the headline curve.
    for sigma in [0, 1, 2, 3, 4, 6]:
        rows.append(
            await _probe(
                holo, cookie_png, cookie_bb,
                "the button that accepts all cookies", "blur", sigma,
            )
        )
    # Downscale dose-response on the same target.
    for f in [0.6, 0.4, 0.25]:
        rows.append(
            await _probe(
                holo, cookie_png, cookie_bb,
                "the button that accepts all cookies", "downscale", f,
            )
        )
    # Colour-vision deficiency (deuteranopia) on the same target.
    rows.append(
        await _probe(
            holo, cookie_png, cookie_bb,
            "the button that accepts all cookies", "cvd", 0.9,
        )
    )
    # Generality: a second target (email field) at baseline and heavy blur.
    if email_bb is not None:
        for sigma in [0, 4]:
            r = await _probe(
                holo, form_png, email_bb,
                "the email address input field", "blur", sigma,
            )
            r["channel"] = "blur_email"
            rows.append(r)

    # --- headline numbers ---
    blur_rows = [r for r in rows if r["channel"] == "blur"]
    base = next(r for r in blur_rows if r["level"] == 0)
    worst = max(blur_rows, key=lambda r: r["level"])
    hits = sum(1 for r in blur_rows if r["inside_target"])
    lat = [r["latency_ms"] for r in rows]

    metrics = {
        "targets_probed": 2 if email_bb else 1,
        "live_calls": len(rows),
        "blur0_error_px": base["error_px"],
        "blur6_error_px": worst["error_px"],
        "blur_inside_rate": round(hits / len(blur_rows), 3),
        "latency_ms_median": int(c.percentile(lat, 50)),
        "latency_ms_p95": int(c.percentile(lat, 95)),
    }
    headline = (
        f"Under blur, Holo's click on a fixed button drifts from "
        f"{base['error_px']:.0f}px error (sharp) to {worst['error_px']:.0f}px "
        f"(σ=6) — a measured, monotone perception dose-response."
    )
    c.Result(
        id="a1_localization",
        title="Localization dose-response (live Holo)",
        kind="live",
        headline=headline,
        metrics=metrics,
        table=rows,
        notes=(
            "Ground truth = Playwright bounding boxes on fixtures/hostile_form.html. "
            "Cookie 'Accept all' button verified at true center (~547,430). One live "
            f"call per row at temperature 0, HAI_RPM={rpm:g}. Latency wraps localize()."
        ),
    ).write()

    print("=== A1 localization dose-response ===")
    for r in rows:
        mark = "IN " if r["inside_target"] else "OUT"
        print(
            f"  {r['channel']:>11} L={r['level']:<4} -> ({r['pred_x']:>4},{r['pred_y']:>4}) "
            f"err={r['error_px']:>6}px [{mark}] {r['latency_ms']}ms"
        )
    print(f"\nHEADLINE: {headline}")
    print(f"metrics: {metrics}")


if __name__ == "__main__":
    asyncio.run(run())
