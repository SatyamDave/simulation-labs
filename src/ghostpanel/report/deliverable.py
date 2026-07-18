"""Hand-deliverable client report — the leave-behind that IS the product.

Simulation Labs' manual audit phase ships ONE artifact to the client: a single,
self-contained ``report.html`` they open as a plain file or link, no server, no
login. This module renders it.

Design goals (see GO_TO_MARKET.md / VISION.md for voice):
  * **Findings first.** Two-to-three written, CRO-framed findings lead the page —
    the interpretation is what justifies the invoice. Everything below them is
    the evidence that backs them up.
  * **Self-contained.** All CSS is inlined, all charts are inline SVG. The only
    external references are *relative* links to the ``.webm`` video receipts that
    live next to the file in the run directory (multi-MB video is never inlined).
  * **On-brand.** Same dark palette / display font as the marketing site so it
    reads as the same company.
  * **Behavioral-segment framing only.** Personas are shown as conversion
    segments (Fluent, Rushed, Misclick-prone, First-timer, Mobile-thumb). This is
    a CRO product; there is no accessibility / impairment language anywhere here.

Public API mirrors ``html_report`` so it is a drop-in for the standard
report-writing path:

    render_deliverable(report, insights=None, personas=None, run_dir=None) -> str
    write_deliverable_report(report, artifact_dir, insights=None, personas=None) -> str

``write_deliverable_report`` writes ``<artifact_dir>/<run_id>/report.html`` and
returns the absolute path — same signature and output location as
``write_html_report``, so wiring the caller to it is a one-line swap.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from jinja2 import Environment, select_autoescape

from ghostpanel_contracts import PersonaConfig, PersonaOutcome, RunReport

from .html_report import _load_run_personas, _media_href, _survival_curve
from .insights import build_insights

# ---------------------------------------------------------------------------
# Brand tokens (kept in one place; injected into the template)
# ---------------------------------------------------------------------------
BRAND = {
    "bg": "#0B0D11",
    "bg_alt": "#0F1218",
    "panel": "#1E2127",
    "blue": "#4C8DFF",
    "blue_hover": "#6AA0FF",
    "cyan": "#39D0E0",
    "text": "#E9EAEC",
    "muted": "#8B9099",
    "border": "#2C3038",
    "ok": "#28C840",
    "fail": "#FF5F57",
    "font": (
        "'Space Grotesk', 'Segoe UI', system-ui, -apple-system, "
        "'Helvetica Neue', Arial, sans-serif"
    ),
    "mono": "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
}

# Canvas used for the heatmap frame + cursor-path scaling. Failure coordinates
# are true viewport pixels; the default swarm viewport is 1280x800.
_VIEWPORT = (1280, 800)

# ---------------------------------------------------------------------------
# Behavioral-segment classification (CRO framing, never impairment framing)
# ---------------------------------------------------------------------------
# One-line "who this is" per segment, for the roster.
SEGMENT_BLURB: dict[str, str] = {
    "Fluent": "Confident, unhurried user — the control the others are measured against.",
    "AI Agent": "An unattended computer-use agent — is your flow machine-navigable?",
    "Rushed": "In a hurry; abandons the moment the path isn't obvious.",
    "Misclick-prone": "Imprecise taps; punished by small or crowded targets.",
    "First-timer": "Unfamiliar with the flow; reads literally, infers nothing.",
    "Mobile-thumb": "Small screen, thumb-driven; reflow and tap-size sensitive.",
}

# Canonical segment tokens that may already appear in a persona name/id
# (the current roster names ARE the segment names).
_CANONICAL = [
    ("misclick", "Misclick-prone"),
    ("mobile", "Mobile-thumb"),
    ("first-timer", "First-timer"),
    ("first timer", "First-timer"),
    ("rushed", "Rushed"),
    ("fluent", "Fluent"),
]

# Perturbation-kind -> segment, in decreasing priority.
_PERT_PRIORITY: list[tuple[str, str]] = [
    ("small_viewport", "Mobile-thumb"),
    ("impatience", "Rushed"),
    ("low_literacy", "First-timer"),
    ("blur", "First-timer"),
    ("downscale", "First-timer"),
    ("cvd", "First-timer"),
    ("tremor", "Misclick-prone"),
]

# Legacy fixture ids/names -> segment, checked as substrings in priority order.
_LEGACY = [
    ("ai-agent", "AI Agent"),
    ("agent", "AI Agent"),
    ("power", "Fluent"),
    ("grandma", "First-timer"),
    ("non-native", "First-timer"),
    ("literacy", "First-timer"),
    ("vision", "First-timer"),
    ("blur", "First-timer"),
    ("colorblind", "First-timer"),
    ("tremor", "Misclick-prone"),
    ("shak", "Misclick-prone"),
    ("impatient", "Rushed"),
    ("rush", "Rushed"),
]


# Words that betray the old impairment framing. This is a CRO product; if a
# persona still carries a legacy display name, we fall back to its segment label
# so no accessibility/impairment wording can ever reach the client page.
_IMPAIRMENT_WORDS = [
    "vision", "tremor", "blind", "impair", "disab", "elderly", "grandma",
    "deaf", "hard of hearing", "motor", "cognitive", "dyslex", "colour blind",
    "color blind", "colorblind", "deuteran", "protan", "tritan", "wheelchair",
]


def _safe_persona_name(name: str, segment: str) -> str:
    """A persona's own display name, but only when it adds clean, non-redundant
    detail. Returns '' when the name equals the segment or carries any legacy
    impairment wording (the segment label is shown instead)."""
    if not name:
        return ""
    low = name.lower()
    if low == segment.lower():
        return ""
    if any(w in low for w in _IMPAIRMENT_WORDS):
        return ""
    return name


def _segment(persona_id: str, persona_name: str, perturbations: list[str]) -> str:
    """Map a persona to a CRO behavioral segment. Prefers an explicit segment
    name on the persona, then its active perturbations, then a legacy-id
    heuristic (for the pre-rename fixture), finally 'Fluent'."""
    hay = f"{persona_id} {persona_name}".lower()
    for token, seg in _CANONICAL:
        if token in hay:
            return seg
    perts = set(perturbations or [])
    if "ai-agent" in hay or persona_id == "ai-agent":
        return "AI Agent"
    for kind, seg in _PERT_PRIORITY:
        if kind in perts:
            return seg
    for token, seg in _LEGACY:
        if token in hay:
            return seg
    return "Fluent"


# ---------------------------------------------------------------------------
# Roster: one enriched record per persona (survival is the complete source;
# results add reason / step trace / media when present)
# ---------------------------------------------------------------------------
_OUTCOME_LABEL = {
    PersonaOutcome.SUCCESS: "completed",
    PersonaOutcome.STEP_BUDGET: "ran out of steps",
    PersonaOutcome.TIME_BUDGET: "ran out of time",
    PersonaOutcome.STUCK: "gave up",
    PersonaOutcome.ERROR: "infra error",
}


def _clean_label(text: str) -> Optional[str]:
    """Pull a UI-control label out of a caption/reason, e.g. the quoted
    'Explore plans' from "Clicked the 'Explore plans' decoy". None if none."""
    if not text:
        return None
    m = re.search(r"['\"‘’“”]([^'\"‘’“”]{2,40})"
                  r"['\"‘’“”]", text)
    if m:
        return m.group(1).strip()
    return None


def _region(x: int, y: int, vw: int, vh: int) -> str:
    col = "left" if x < vw / 3 else ("centre" if x < 2 * vw / 3 else "right")
    row = "top" if y < vh / 3 else ("middle" if y < 2 * vh / 3 else "bottom")
    return f"{row}-{col}"


def _build_roster(
    report: RunReport, perts_by_id: dict[str, list[str]], run_dir: Optional[Path]
) -> list[dict]:
    results_by_id = {r.persona_id: r for r in report.results}
    heat_by_id: dict[str, tuple[int, int]] = {}
    for h in report.heatmap_points:
        heat_by_id.setdefault(h.persona_id, (h.x, h.y))

    roster: list[dict] = []
    for sp in report.survival:
        res = results_by_id.get(sp.persona_id)
        coords = None
        if res is not None and res.failure_coords is not None:
            coords = tuple(res.failure_coords)
        elif sp.persona_id in heat_by_id:
            coords = heat_by_id[sp.persona_id]

        step = None
        reason = ""
        last_caption = ""
        trace: list[dict] = []
        media: dict[str, Optional[str]] = {"video": None, "audio": None}
        if res is not None:
            step = res.failure_step
            reason = res.failure_reason or ""
            media = {
                "video": _media_href(res.video_path, run_dir),
                "audio": _media_href(res.audio_path, run_dir),
            }
            for st in res.steps:
                a = st.action
                trace.append(
                    {
                        "step": st.step,
                        "caption": a.caption or a.type.value,
                        "x": a.x,
                        "y": a.y,
                        "type": a.type.value,
                    }
                )
            if res.steps and res.steps[-1].action.caption:
                last_caption = res.steps[-1].action.caption
        if step is None:
            step = sp.steps_survived

        segment = _segment(
            sp.persona_id, sp.persona_name, perts_by_id.get(sp.persona_id, [])
        )
        display_name = _safe_persona_name(sp.persona_name, segment)
        roster.append(
            {
                "persona_id": sp.persona_id,
                "display_name": display_name,
                "who": segment + (f" ({display_name})" if display_name else ""),
                "segment": segment,
                "outcome": sp.outcome,
                "outcome_label": _OUTCOME_LABEL.get(sp.outcome, sp.outcome.value),
                "completed": sp.completed,
                "steps_survived": sp.steps_survived,
                "coords": coords,
                "step": step,
                "reason": reason,
                "last_caption": last_caption,
                "trace": trace,
                "media": media,
            }
        )
    return roster


# ---------------------------------------------------------------------------
# Findings — the lead. Derived from the roster; CRO language only.
# ---------------------------------------------------------------------------
def _seg_phrase(segments: list[str]) -> str:
    segs = list(dict.fromkeys(segments))  # dedupe, keep order
    if len(segs) == 1:
        return f"{segs[0]} users"
    if len(segs) == 2:
        return f"{segs[0]} and {segs[1]} users"
    return "Multiple segments"


def _cluster(points: list[dict], radius: int = 70) -> list[list[dict]]:
    """Single-linkage clustering of death points by pixel proximity."""
    clusters: list[list[dict]] = []
    for p in points:
        placed = False
        for c in clusters:
            if any(
                (p["coords"][0] - q["coords"][0]) ** 2
                + (p["coords"][1] - q["coords"][1]) ** 2
                <= radius * radius
                for q in c
            ):
                c.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])
    return clusters


def _cluster_finding(roster: list[dict], non_error: int, vw: int, vh: int):
    dead = [r for r in roster if not r["completed"] and r["coords"] is not None
            and r["outcome"] != PersonaOutcome.ERROR]
    if not dead:
        return None
    clusters = _cluster(dead)
    best = max(clusters, key=len)
    if len(best) < 2:
        return None  # a single isolated death isn't a "pattern" finding
    xs = [r["coords"][0] for r in best]
    ys = [r["coords"][1] for r in best]
    cx, cy = round(sum(xs) / len(xs)), round(sum(ys) / len(ys))
    region = _region(cx, cy, vw, vh)
    label = None
    for r in best:
        label = _clean_label(r["reason"]) or _clean_label(r["last_caption"])
        if label:
            break
    segs = [r["segment"] for r in best]
    phrase = _seg_phrase(segs)
    # Only attribute the specific mistake "label" to the segments that ACTUALLY
    # produced it — not the whole cluster. A single persona's reason must not be
    # asserted about segments with no evidence for it (it's a receipt, not a
    # guess). Use the labelled headline only when those segments are the cluster
    # majority; otherwise fall back to the neutral location headline.
    labeled = [
        r for r in best
        if (_clean_label(r["reason"]) or _clean_label(r["last_caption"])) == label
    ] if label else []
    if label and len(labeled) >= max(2, (len(best) + 1) // 2):
        headline = (
            f"{_seg_phrase([r['segment'] for r in labeled])} mistake “{label}” "
            f"for the primary action and abandon"
        )
    else:
        headline = f"{phrase} abandon at a single control in the {region} of the page"
    evidence = [
        (
            f"{r['who']} {r['outcome_label']} at step "
            f"{r['step']}, pixel ({r['coords'][0]}, {r['coords'][1]})"
            + (f" — {r['reason']}" if r["reason"] else "")
        )
        for r in best
    ]
    pct = round(100 * len(best) / non_error) if non_error else 0
    impact = (
        f"That's {pct}% of the tested panel dying inside a {70}px radius in the "
        f"{region} of the page. On live traffic this reads as unexplained drop-off "
        f"concentrated on one control — the highest-leverage fix on the page."
    )
    return {"headline": headline, "evidence": evidence, "impact": impact,
            "coords": (cx, cy)}


def _budget_finding(roster: list[dict], fastest_success: Optional[int]):
    burned = [
        r for r in roster
        if r["outcome"] in (PersonaOutcome.STEP_BUDGET, PersonaOutcome.TIME_BUDGET)
    ]
    if not burned:
        return None
    segs = [r["segment"] for r in burned]
    phrase = _seg_phrase(segs)
    headline = f"{phrase} exhaust their patience before reaching the goal"
    evidence = [
        f"{r['who']} {r['outcome_label']} after "
        f"{r['steps_survived']} steps without completing"
        for r in burned
    ]
    impact = (
        "These segments are time- and step-sensitive: every extra hop, modal, or "
        "slow response compounds against them."
    )
    if fastest_success:
        impact += (
            f" A confident user clears the flow in {fastest_success} steps — "
            "trimming steps and latency is what recovers this segment."
        )
    return {"headline": headline, "evidence": evidence, "impact": impact}


def _contrast_finding(roster: list[dict], fastest_success: Optional[int]):
    wins = [r for r in roster if r["completed"]]
    losses = [r for r in roster
              if not r["completed"] and r["outcome"] != PersonaOutcome.ERROR]
    if not wins or not losses:
        return None
    headline = (
        "The flow works end to end — the losses are comprehension gaps, "
        "not broken functionality"
    )
    evidence = [
        f"{r['who']} completed the task"
        + (f" in {r['steps_survived']} steps" if r["steps_survived"] else "")
        for r in wins
    ]
    agent_won = any(r["segment"] == "AI Agent" for r in wins)
    impact = (
        f"{len(wins)} of {len(wins) + len(losses)} segments finish the task"
        + (", including an unattended AI agent" if agent_won else "")
        + ". Because the mechanics work, the "
        f"{len(losses)} failing segment(s) are hitting layout, labelling, and copy "
        "ambiguity — fixable without touching the backend."
    )
    return {"headline": headline, "evidence": evidence, "impact": impact}


def _rage_finding(roster: list[dict]):
    hits = [
        r for r in roster
        if not r["completed"]
        and re.search(r"three times|repeat|again|kept |over and over|multiple times",
                      r["reason"], re.I)
    ]
    if not hits:
        return None
    r = hits[0]
    label = _clean_label(r["reason"]) or _clean_label(r["last_caption"])
    target = f"“{label}”" if label else "the same control"
    headline = f"{r['segment']} users re-tap {target} when the UI gives no feedback"
    evidence = [
        f"{r['who']} {r['reason']}"
        for r in hits
    ]
    impact = (
        "A repeated identical tap means the interface never signalled that the first "
        "one failed — add a visible state change or error so users aren't left "
        "guessing."
    )
    return {"headline": headline, "evidence": evidence, "impact": impact}


def build_findings(roster: list[dict], insights: dict, vw: int, vh: int) -> list[dict]:
    """Two-to-three CRO findings, most-actionable first. Always returns at least
    one item so the report leads with an interpretation."""
    non_error = sum(1 for r in roster if r["outcome"] != PersonaOutcome.ERROR)
    fastest = ((insights or {}).get("stats", {}).get("run", {})
               .get("fastest_success_steps"))
    candidates = [
        _cluster_finding(roster, non_error, vw, vh),
        _budget_finding(roster, fastest),
        _contrast_finding(roster, fastest),
        _rage_finding(roster),
    ]
    findings = [f for f in candidates if f][:3]
    if findings:
        return findings

    # Fallbacks so the lead is never empty.
    losses = [r for r in roster
              if not r["completed"] and r["outcome"] != PersonaOutcome.ERROR]
    if not losses and non_error:
        return [{
            "headline": "Clean sweep — every tested segment completed the task",
            "evidence": [
                f"{r['who']} completed the task"
                for r in roster if r["completed"]
            ],
            "impact": (
                "No abandonment in this run. Re-run after each deploy to catch a "
                "regression the moment it ships."
            ),
        }]
    # Some failures but none clustered / budgeted / contrasted.
    return [{
        "headline": _seg_phrase([r["segment"] for r in losses])
        + " abandon before completing the task",
        "evidence": [
            f"{r['who']} {r['outcome_label']} at step "
            f"{r['step']}" + (f" — {r['reason']}" if r["reason"] else "")
            for r in losses
        ],
        "impact": "These segments never reach the goal — the funnel leaks here.",
    }]


# ---------------------------------------------------------------------------
# Visual evidence geometry (built in Python; rendered as inline SVG)
# ---------------------------------------------------------------------------
def _heatmap(points: list[dict], vw: int, vh: int, width: int = 720):
    """Scale death coordinates onto a viewport-proportioned canvas. Each point
    is a warm 'blob'; overlap naturally intensifies (classic abandonment heat).

    Each death is normalised by ITS OWN persona's viewport (a mobile persona ran
    at 390x844, not the 1280x800 canvas frame), so a small-screen death lands at
    the right relative spot instead of being squashed or clipped off-canvas.
    Infra ERROR personas are excluded — they never abandoned, so plotting them as
    heat would contradict the verdict and hero counts."""
    height = round(width * vh / vw)
    blobs = []
    for p in points:
        if p["coords"] is None:
            continue
        if p.get("outcome") == PersonaOutcome.ERROR:
            continue  # infra failure is not an abandonment
        pvw = p.get("vw") or vw
        pvh = p.get("vh") or vh
        # fraction of this persona's own viewport -> position on the canvas
        cx = min(max(p["coords"][0] / pvw, 0.0), 1.0) * width
        cy = min(max(p["coords"][1] / pvh, 0.0), 1.0) * height
        blobs.append(
            {
                "cx": round(cx, 1),
                "cy": round(cy, 1),
                "segment": p["segment"],
                "label": p["who"],
            }
        )
    return {"width": width, "height": height, "blobs": blobs}


def _cursor_path(trace: list[dict], vw: int, vh: int, width: int = 300):
    """Ordered click coordinates for a persona -> a mini cursor-path SVG.

    ``vw``/``vh`` are THIS persona's own viewport (a mobile persona ran at
    390x844), so the path is placed by viewport fraction and never clipped."""
    pts = [(t["x"], t["y"], t["caption"]) for t in trace
           if t["x"] is not None and t["y"] is not None]
    if len(pts) < 1:
        return None
    height = round(width * vh / vw)
    scaled = [
        {
            "x": round(min(max(x / vw, 0.0), 1.0) * width, 1),
            "y": round(min(max(y / vh, 0.0), 1.0) * height, 1),
            "n": i + 1, "caption": cap,
        }
        for i, (x, y, cap) in enumerate(pts)
    ]
    poly = " ".join(f"{s['x']},{s['y']}" for s in scaled)
    return {"width": width, "height": height, "points": scaled, "poly": poly}


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------
_env = Environment(autoescape=select_autoescape(["html", "xml"]))

_TEMPLATE = _env.from_string(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulation Labs — {{ report.task }}</title>
<style>
  :root {
    --bg: {{ c.bg }}; --bg-alt: {{ c.bg_alt }}; --panel: {{ c.panel }};
    --blue: {{ c.blue }}; --blue-hover: {{ c.blue_hover }}; --cyan: {{ c.cyan }};
    --text: {{ c.text }}; --muted: {{ c.muted }}; --border: {{ c.border }};
    --ok: {{ c.ok }}; --fail: {{ c.fail }};
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font-family: {{ c.font }}; line-height: 1.55;
         -webkit-font-smoothing: antialiased; }
  .wrap { max-width: 900px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }
  a { color: var(--blue); text-decoration: none; }
  a:hover { color: var(--blue-hover); text-decoration: underline; }
  .mono { font-family: {{ c.mono }}; font-size: .82rem; }
  .muted { color: var(--muted); }

  /* header */
  .brand { display: flex; align-items: center; gap: .6rem; font-weight: 700;
           letter-spacing: -.01em; font-size: 1.05rem; }
  .brand .dot { width: 10px; height: 10px; border-radius: 50%;
                background: var(--cyan); box-shadow: 0 0 12px var(--cyan); }
  .brand .tag { color: var(--muted); font-weight: 500; font-size: .8rem; }
  h1 { font-size: 2rem; font-weight: 700; letter-spacing: -.02em;
       margin: 1.6rem 0 .4rem; }
  .meta { color: var(--muted); font-size: .88rem; }
  .meta strong { color: var(--text); font-weight: 600; }
  .rule { height: 1px; background: var(--border); border: 0; margin: 2.2rem 0; }

  /* hero */
  .hero { display: flex; flex-wrap: wrap; gap: 1rem; margin: 2rem 0 .5rem; }
  .hero-card { background: var(--bg-alt); border: 1px solid var(--border);
               border-radius: 14px; padding: 1.3rem 1.5rem; flex: 1; min-width: 200px; }
  .hero-num { font-size: 2.8rem; font-weight: 700; letter-spacing: -.03em;
              line-height: 1; }
  .hero-num.ok { color: var(--ok); } .hero-num.warn { color: var(--fail); }
  .hero-num.blue { color: var(--cyan); }
  .hero-label { color: var(--muted); font-size: .82rem; margin-top: .5rem; }
  .verdict { font-size: 1.05rem; margin: 1.4rem 0 0; }

  /* sections */
  h2 { font-size: 1.3rem; font-weight: 700; letter-spacing: -.01em;
       margin: 0 0 .3rem; }
  .kicker { color: var(--cyan); font-size: .72rem; font-weight: 700;
            letter-spacing: .12em; text-transform: uppercase; }
  section { margin: 3rem 0; }
  .lede { color: var(--muted); font-size: .92rem; margin: .2rem 0 1.4rem; }

  /* findings */
  .finding { background: var(--panel); border: 1px solid var(--border);
             border-left: 3px solid var(--blue); border-radius: 12px;
             padding: 1.4rem 1.6rem; margin: 1rem 0; }
  .finding .idx { color: var(--muted); font-size: .74rem; font-weight: 700;
                  letter-spacing: .1em; text-transform: uppercase; }
  .finding h3 { font-size: 1.2rem; font-weight: 700; letter-spacing: -.01em;
                margin: .35rem 0 .9rem; line-height: 1.35; }
  .ev-head, .why-head { font-size: .72rem; font-weight: 700; letter-spacing: .1em;
             text-transform: uppercase; color: var(--muted); margin: .8rem 0 .35rem; }
  .finding ul { margin: 0; padding-left: 1.1rem; }
  .finding li { margin: .2rem 0; font-size: .9rem; }
  .finding .why { font-size: .95rem; }

  /* chart panels */
  .panel { background: var(--bg-alt); border: 1px solid var(--border);
           border-radius: 14px; padding: 1.4rem; overflow-x: auto; }
  .frame { background:
      repeating-linear-gradient(0deg, transparent, transparent 39px, {{ c.border }}44 39px, {{ c.border }}44 40px),
      repeating-linear-gradient(90deg, transparent, transparent 39px, {{ c.border }}44 39px, {{ c.border }}44 40px),
      var(--bg); border: 1px solid var(--border); border-radius: 8px;
      display: inline-block; position: relative; }
  .legend { display: flex; flex-wrap: wrap; gap: .5rem 1.1rem; margin-top: 1rem;
            font-size: .82rem; color: var(--muted); }
  .legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                margin-right: .4rem; vertical-align: middle; background: var(--fail); }

  /* roster / traces */
  .seg { display: grid; grid-template-columns: 1fr; gap: 1rem; }
  .seg-card { background: var(--panel); border: 1px solid var(--border);
              border-radius: 12px; padding: 1.2rem 1.4rem; }
  .seg-top { display: flex; align-items: center; flex-wrap: wrap; gap: .6rem; }
  .badge { font-size: .72rem; font-weight: 700; letter-spacing: .04em;
           padding: .2rem .6rem; border-radius: 999px; border: 1px solid var(--border);
           color: var(--cyan); background: {{ c.cyan }}14; }
  .seg-name { font-weight: 600; }
  .pill { font-size: .74rem; font-weight: 700; padding: .15rem .55rem;
          border-radius: 999px; margin-left: auto; }
  .pill.ok { color: var(--ok); background: {{ c.ok }}1c; }
  .pill.fail { color: var(--fail); background: {{ c.fail }}1c; }
  .seg-blurb { color: var(--muted); font-size: .85rem; margin: .5rem 0 0; }
  .seg-body { display: flex; gap: 1.4rem; flex-wrap: wrap; margin-top: 1rem;
              align-items: flex-start; }
  .trace { flex: 1; min-width: 240px; }
  .trace ol { margin: 0; padding-left: 1.2rem; font-size: .85rem; }
  .trace li { margin: .12rem 0; }
  .trace .pt { color: var(--muted); }
  .receipts { font-size: .85rem; margin-top: .8rem; }
  .receipts .none { color: var(--muted); }
  .stat-inline { color: var(--muted); font-size: .85rem; margin-top: .4rem; }
  .stat-inline b { color: var(--text); }

  /* axis text */
  text.axis { font-size: 11px; fill: {{ c.muted }}; }
  footer { color: var(--muted); font-size: .82rem; border-top: 1px solid var(--border);
           padding-top: 1.4rem; margin-top: 3.5rem; }
</style>
</head>
<body>
<div class="wrap">

  <div class="brand"><span class="dot"></span>Simulation Labs
    <span class="tag">&nbsp;/ behavioral conversion audit</span></div>

  <h1>{{ report.task }}</h1>
  <div class="meta">
    Target <strong>{{ report.target_url }}</strong><br>
    {{ successes }} of {{ non_error }} behavioral segments completed the task
    &middot; run <span class="mono">{{ report.run_id }}</span>
    &middot; {{ generated }}
  </div>

  <div class="hero">
    <div class="hero-card">
      <div class="hero-num {{ 'ok' if completion_pct >= 80 else 'warn' }}">{{ completion_pct }}%</div>
      <div class="hero-label">of tested segments completed the task</div>
    </div>
    {% if score is not none %}
    <div class="hero-card">
      <div class="hero-num blue">{{ score }}</div>
      <div class="hero-label">Simulation Score / 100 &mdash; survival-weighted composite</div>
    </div>
    {% endif %}
    <div class="hero-card">
      <div class="hero-num {{ 'warn' if abandoned else 'ok' }}">{{ abandoned }}</div>
      <div class="hero-label">segment{{ '' if abandoned == 1 else 's' }} abandoned before finishing</div>
    </div>
  </div>
  <p class="verdict">{{ verdict }}</p>

  <hr class="rule">

  <!-- ============ FINDINGS (the lead) ============ -->
  <section>
    <div class="kicker">What we found</div>
    <h2>Findings</h2>
    <p class="lede">The interpretation, first. Each finding names the segments
      affected, the exact evidence from their action traces, and why it costs you
      conversions. Supporting charts follow below.</p>
    {% for f in findings %}
    <div class="finding">
      <div class="idx">Finding {{ loop.index }} of {{ findings | length }}</div>
      <h3>{{ f.headline }}</h3>
      <div class="ev-head">Evidence</div>
      <ul>{% for e in f.evidence %}<li>{{ e }}</li>{% endfor %}</ul>
      <div class="why-head">Why it matters</div>
      <p class="why">{{ f.impact }}</p>
    </div>
    {% endfor %}
  </section>

  <!-- ============ HEATMAP ============ -->
  <section>
    <div class="kicker">Where they die</div>
    <h2>Abandonment heatmap</h2>
    <p class="lede">Every point is one segment's last recorded pixel before it gave
      up, placed on your {{ vw }}&times;{{ vh }} viewport. Overlap glows hotter.</p>
    <div class="panel">
    {% if heatmap.blobs %}
      <svg class="frame" width="{{ heatmap.width }}" height="{{ heatmap.height }}"
           role="img" aria-label="Abandonment heatmap">
        <defs>
          <radialGradient id="heat" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="{{ c.fail }}" stop-opacity="0.85"/>
            <stop offset="45%" stop-color="{{ c.fail }}" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="{{ c.fail }}" stop-opacity="0"/>
          </radialGradient>
        </defs>
        {% for b in heatmap.blobs %}
        <circle cx="{{ b.cx }}" cy="{{ b.cy }}" r="58" fill="url(#heat)"/>
        {% endfor %}
        {% for b in heatmap.blobs %}
        <circle cx="{{ b.cx }}" cy="{{ b.cy }}" r="5" fill="{{ c.fail }}"
                stroke="{{ c.bg }}" stroke-width="1.5"/>
        <text class="axis" x="{{ b.cx + 9 }}" y="{{ b.cy + 4 }}"
              fill="{{ c.text }}">{{ b.segment }}</text>
        {% endfor %}
      </svg>
      <div class="legend"><span><span class="sw"></span>last pixel before
        abandonment &mdash; brighter = more segments died there</span></div>
    {% else %}
      <p class="muted">No abandonment points recorded &mdash; every segment
        completed the task.</p>
    {% endif %}
    </div>
  </section>

  <!-- ============ SURVIVAL CURVE ============ -->
  {% if curve %}
  <section>
    <div class="kicker">How far they got</div>
    <h2>Survival curve</h2>
    <p class="lede">Segments still in the flow at each step. A cliff marks a step
      where several segments abandon at once.</p>
    <div class="panel">
      <svg width="{{ curve.width }}" height="{{ curve.height }}" role="img"
           aria-label="Stepped survival curve: segments alive by step">
        <line x1="{{ curve.x0 }}" y1="{{ curve.y0 }}" x2="{{ curve.x1 }}"
              y2="{{ curve.y0 }}" stroke="{{ c.border }}"/>
        <line x1="{{ curve.x0 }}" y1="{{ curve.y0 }}" x2="{{ curve.x0 }}"
              y2="{{ curve.y1 }}" stroke="{{ c.border }}"/>
        <path d="{{ curve.path }}" fill="none" stroke="{{ c.blue }}"
              stroke-width="2.5" stroke-linejoin="round"/>
        <text class="axis" x="{{ curve.x0 }}" y="{{ curve.y0 + 16 }}">0</text>
        <text class="axis" x="{{ curve.x1 }}" y="{{ curve.y0 + 16 }}"
              text-anchor="end">{{ curve.max_step }} steps</text>
        <text class="axis" x="{{ curve.x0 - 8 }}" y="{{ curve.y1 + 4 }}"
              text-anchor="end">{{ curve.max_alive }}</text>
        <text class="axis" x="{{ curve.x0 - 8 }}" y="{{ curve.y0 + 4 }}"
              text-anchor="end">0</text>
      </svg>
    </div>
  </section>
  {% endif %}

  <!-- ============ SEGMENT-BY-SEGMENT ============ -->
  <section>
    <div class="kicker">Segment by segment</div>
    <h2>The panel</h2>
    <p class="lede">Each segment is a computer-use agent constrained to model one
      real-world behaviour &mdash; browsing speed, tap precision, familiarity,
      screen size. It either completes your task or abandons at a specific pixel.</p>
    <div class="seg">
    {% for r in roster %}
      <div class="seg-card">
        <div class="seg-top">
          <span class="badge">{{ r.segment }}</span>
          {% if r.display_name %}<span class="seg-name muted">{{ r.display_name }}</span>{% endif %}
          <span class="pill {{ 'ok' if r.completed else 'fail' }}">{{ r.outcome_label }}</span>
        </div>
        <p class="seg-blurb">{{ blurbs.get(r.segment, '') }}</p>
        <div class="seg-body">
          {% if r.cursor %}
          <div>
            <svg class="frame" width="{{ r.cursor.width }}" height="{{ r.cursor.height }}"
                 role="img" aria-label="Cursor path for {{ r.who }}">
              <polyline points="{{ r.cursor.poly }}" fill="none"
                        stroke="{{ c.blue }}" stroke-width="1.5"
                        stroke-dasharray="3 3" opacity="0.8"/>
              {% for p in r.cursor.points %}
              <circle cx="{{ p.x }}" cy="{{ p.y }}" r="7"
                      fill="{{ c.blue if not loop.last or r.completed else c.fail }}"
                      opacity="0.9"/>
              <text x="{{ p.x }}" y="{{ p.y + 3 }}" text-anchor="middle"
                    font-size="9" fill="{{ c.bg }}" font-weight="700">{{ p.n }}</text>
              {% endfor %}
            </svg>
          </div>
          {% endif %}
          <div class="trace">
            {% if r.trace %}
            <ol>
            {% for t in r.trace %}
              <li>{{ t.caption }}
                {% if t.x is not none %}<span class="pt mono">({{ t.x }}, {{ t.y }})</span>{% endif %}
              </li>
            {% endfor %}
            </ol>
            {% endif %}
            <div class="stat-inline">
              Survived <b>{{ r.steps_survived }}</b> step{{ '' if r.steps_survived == 1 else 's' }}
              {% if not r.completed and r.coords %}
                &middot; last pixel <b class="mono">({{ r.coords[0] }}, {{ r.coords[1] }})</b>
              {% endif %}
            </div>
            {% if not r.completed and r.reason %}
            <div class="stat-inline">{{ r.reason }}</div>
            {% endif %}
            <div class="receipts">
              {% if r.media.video %}<a href="{{ r.media.video }}">&#9654; Watch the video receipt (.webm)</a>{% endif %}
              {% if r.media.video and r.media.audio %} &middot; {% endif %}
              {% if r.media.audio %}<a href="{{ r.media.audio }}">&#9834; Exit interview (.wav)</a>{% endif %}
              {% if not r.media.video and not r.media.audio %}<span class="none">Receipts available on request.</span>{% endif %}
            </div>
          </div>
        </div>
      </div>
    {% endfor %}
    </div>
  </section>

  <footer>
    <strong>Method.</strong> Simulation Labs points a swarm of computer-use agents
    at your live flow. Each agent's perception and actuation are mechanically
    constrained to model a distinct conversion segment &mdash; not roleplay. The
    result is what the segment <em>did</em>, grounded in a real action trace, with
    video receipts alongside this file.
    <br><br>
    Prepared for the client &middot; run <span class="mono">{{ report.run_id }}</span>
    &middot; {{ generated }} &middot; contract {{ report.contract_version }}
  </footer>
</div>
</body>
</html>
"""
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _survival_series_from_report(report: RunReport) -> list[dict]:
    """Stepped survival series over ALL non-error survival points (the complete
    roster). More reliable than insights' results-derived series when the report
    carries a survival summary without a full per-persona result list."""
    entries = [
        (sp.completed, sp.steps_survived)
        for sp in report.survival
        if sp.outcome != PersonaOutcome.ERROR
    ]
    if not entries:
        return []
    max_step = max(s for _, s in entries) or 0
    return [
        {"step": step,
         "alive": sum(1 for ok, s in entries if ok or s >= step)}
        for step in range(max_step + 1)
    ]


def _verdict(report: RunReport, successes: int, non_error: int, abandoned: int) -> str:
    task = report.task.rstrip(".")
    if abandoned == 0 and non_error:
        return f"Every tested segment completed “{task}.”"
    return (
        f"{abandoned} of {non_error} tested segments silently abandoned before "
        f"finishing “{task}” — here is exactly where, and why."
    )


def render_deliverable(
    report: RunReport,
    insights: Optional[dict] = None,
    personas: Optional[list[PersonaConfig]] = None,
    run_dir: Optional[str | Path] = None,
) -> str:
    """Render the hand-deliverable client report as a single self-contained HTML
    string. ``insights`` is optional (computed if absent); ``run_dir`` relativises
    the media hrefs to the file's own directory."""
    run_dir_path = Path(run_dir) if run_dir is not None else None

    if insights is None:
        resolved = personas if personas is not None else _load_run_personas(report)
        insights = build_insights(report, resolved or [])

    perts_by_id = {
        p["persona_id"]: p.get("perturbations", [])
        for p in (insights or {}).get("stats", {}).get("personas", [])
    }
    # Each persona's OWN viewport (mobile ran at 390x844); default to the canvas
    # frame when unknown, so heatmap/cursor coords place by viewport fraction.
    resolved_personas = personas if personas is not None else _load_run_personas(report)
    viewport_by_id = {
        p.id: (p.viewport.width, p.viewport.height) for p in (resolved_personas or [])
    }
    vw, vh = _VIEWPORT
    roster = _build_roster(report, perts_by_id, run_dir_path)
    for r in roster:
        r["vw"], r["vh"] = viewport_by_id.get(r["persona_id"], (vw, vh))
        r["cursor"] = _cursor_path(r["trace"], r["vw"], r["vh"])

    findings = build_findings(roster, insights or {}, vw, vh)

    non_error = sum(1 for r in roster if r["outcome"] != PersonaOutcome.ERROR)
    successes = sum(1 for r in roster if r["completed"])
    abandoned = non_error - successes

    curve = _survival_curve(_survival_series_from_report(report))
    heatmap = _heatmap(roster, vw, vh)

    return _TEMPLATE.render(
        report=report,
        c=BRAND,
        blurbs=SEGMENT_BLURB,
        findings=findings,
        roster=roster,
        curve=curve,
        heatmap=heatmap,
        vw=vw,
        vh=vh,
        completion_pct=round(report.completion_rate * 100),
        score=(insights or {}).get("ghostpanel_score"),
        successes=successes,
        non_error=non_error,
        abandoned=abandoned,
        verdict=_verdict(report, successes, non_error, abandoned),
        generated=report.generated_at or "",
    )


def write_deliverable_report(
    report: RunReport,
    artifact_dir: str | Path,
    insights: Optional[dict] = None,
    personas: Optional[list[PersonaConfig]] = None,
) -> str:
    """Render and write the deliverable to ``<artifact_dir>/<run_id>/report.html``.

    Drop-in for ``html_report.write_html_report`` (same signature, same output
    path). Returns the absolute path to the written file. The ``.webm`` / ``.wav``
    receipts are expected to live in the same run directory and are linked
    relatively.
    """
    out_dir = Path(artifact_dir) / report.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.html"
    path.write_text(
        render_deliverable(
            report, insights=insights, personas=personas, run_dir=out_dir
        ),
        encoding="utf-8",
    )
    return str(path)
