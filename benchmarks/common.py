"""Shared utilities for the Ghostpanel benchmark suite.

Everything the individual b_*.py benchmarks need in common lives here so the
per-benchmark modules stay small and never duplicate plumbing:

* paths + .env loading
* persona loading (real personas/*.json via the engine loader)
* numpy stat helpers (percentile, mean/std, Wilson CI for proportions)
* a standard result envelope + JSON writer (results/<id>.json)
* ground-truth capture: render a page with Playwright and return the screenshot
  bytes plus every element's true-pixel bounding box (for localization accuracy)
* an HTML report renderer that aggregates every results/*.json into one page
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

# --------------------------------------------------------------------------- paths
REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"
PERSONAS_DIR = REPO_ROOT / "personas"
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
HOSTILE_FORM = FIXTURES / "hostile_form.html"


def load_env() -> None:
    """Load the repo .env into os.environ (no-op if python-dotenv missing)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(REPO_ROOT / ".env")


# --------------------------------------------------------------------------- personas
def load_all_personas():
    """All real personas/*.json as PersonaConfig, in a stable order."""
    from ghostpanel.engine.personas import load_personas

    return sorted(load_personas(), key=lambda p: p.id)


def load_persona(pid: str):
    from ghostpanel.engine.personas import load_personas

    (p,) = load_personas(ids=[pid])
    return p


# --------------------------------------------------------------------------- stats
def mean(xs: Iterable[float]) -> float:
    a = np.asarray(list(xs), dtype=float)
    return float(a.mean()) if a.size else 0.0


def std(xs: Iterable[float]) -> float:
    a = np.asarray(list(xs), dtype=float)
    return float(a.std(ddof=0)) if a.size else 0.0


def percentile(xs: Iterable[float], q: float) -> float:
    a = np.asarray(list(xs), dtype=float)
    return float(np.percentile(a, q)) if a.size else 0.0


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion — honest error bars on rates."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


# --------------------------------------------------------------------------- geometry
@dataclass
class BBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def dist_to_center(self, px: float, py: float) -> float:
        return math.hypot(px - self.cx, py - self.cy)

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


# --------------------------------------------------------------------------- ground truth
async def capture_ground_truth(
    file_url: str,
    selectors: dict[str, str],
    viewport: tuple[int, int] = (1280, 800),
):
    """Render `file_url` headless, return (png_bytes, {label: BBox}).

    Bounding boxes are in true viewport pixels — the exact space LiveHoloClient
    denormalizes Holo's 0-1000 coords into. Only visible, box-having selectors
    are returned.
    """
    from playwright.async_api import async_playwright

    w, h = viewport
    boxes: dict[str, BBox] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": w, "height": h})
        await page.goto(file_url, wait_until="networkidle")
        png = await page.screenshot()
        for label, sel in selectors.items():
            loc = page.locator(sel).first
            try:
                if await loc.count() == 0:
                    continue
                box = await loc.bounding_box()
            except Exception:
                box = None
            if box and box["width"] > 0 and box["height"] > 0:
                boxes[label] = BBox(box["x"], box["y"], box["width"], box["height"])
        await browser.close()
    return png, boxes


def hostile_form_url() -> str:
    return HOSTILE_FORM.resolve().as_uri()


# Semantic ground-truth targets on the hostile form (label -> CSS selector).
# These are the dark-pattern traps the localization benchmark probes.
HOSTILE_TARGETS = {
    "real_submit": "form button.btn-real",       # grey/secondary "Create account" (correct)
    "decoy_button": "form button.btn-decoy",      # blue/primary "Explore plans" (trap)
    "email_input": "#email",
    "cookie_accept": "#cookie button",
}


# --------------------------------------------------------------------------- results
@dataclass
class Result:
    """Standard envelope every benchmark writes."""

    id: str
    title: str
    kind: str                       # "offline" | "live" | "analytic"
    headline: str                   # one-sentence quotable number
    metrics: dict[str, Any] = field(default_factory=dict)
    table: list[dict] = field(default_factory=list)  # rows for a chart/table
    notes: str = ""

    def write(self) -> Path:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"{self.id}.json"
        payload = {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "headline": self.headline,
            "metrics": self.metrics,
            "table": self.table,
            "notes": self.notes,
        }
        path.write_text(json.dumps(payload, indent=2, default=_json_default))
        return path


def _json_default(o: Any):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not serializable: {type(o)}")


def load_results() -> list[dict]:
    if not RESULTS_DIR.exists():
        return []
    out = []
    for p in sorted(RESULTS_DIR.glob("*.json")):
        out.append(json.loads(p.read_text()))
    return out


def build_report(out_path: Optional[Path] = None) -> Path:
    """Aggregate every results/*.json into a single self-contained HTML page."""
    out_path = out_path or (RESULTS_DIR / "report.html")
    results = load_results()
    cards = []
    for r in results:
        rows = ""
        if r.get("table"):
            cols = list(r["table"][0].keys())
            head = "".join(f"<th>{c}</th>" for c in cols)
            body = "".join(
                "<tr>" + "".join(f"<td>{_fmt(row.get(c))}</td>" for c in cols) + "</tr>"
                for row in r["table"]
            )
            rows = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        metrics = "".join(
            f"<div class=metric><span class=k>{k}</span><span class=v>{_fmt(v)}</span></div>"
            for k, v in r.get("metrics", {}).items()
        )
        cards.append(
            f"""<section class=card>
  <div class=kind data-kind="{r['kind']}">{r['kind']}</div>
  <h2>{r['title']}</h2>
  <p class=headline>{r['headline']}</p>
  <div class=metrics>{metrics}</div>
  {rows}
  {'<p class=notes>' + r['notes'] + '</p>' if r.get('notes') else ''}
</section>"""
        )
    html = _REPORT_SHELL.replace("__CARDS__", "\n".join(cards)).replace(
        "__N__", str(len(results))
    )
    out_path.write_text(html)
    return out_path


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.3g}"
    return "" if v is None else str(v)


_REPORT_SHELL = """<!doctype html><html><head><meta charset=utf-8>
<title>Ghostpanel Benchmarks</title><style>
:root{color-scheme:light dark}
body{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.6rem}.sub{opacity:.65;margin-top:-.5rem}
.card{border:1px solid #8883;border-radius:12px;padding:1rem 1.25rem;margin:1rem 0}
.kind{display:inline-block;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;
 padding:.15rem .5rem;border-radius:999px;background:#8882}
.kind[data-kind=live]{background:#e0242433;color:#e02424}
.kind[data-kind=offline]{background:#22884433;color:#228844}
.kind[data-kind=analytic]{background:#2266cc33;color:#2266cc}
h2{font-size:1.15rem;margin:.4rem 0}
.headline{font-size:1.05rem;font-weight:600}
.metrics{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0}
.metric{background:#8881;border-radius:8px;padding:.35rem .6rem;font-size:.85rem}
.metric .k{opacity:.6;margin-right:.4rem}.metric .v{font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.85rem;margin-top:.5rem}
th,td{border:1px solid #8883;padding:.3rem .5rem;text-align:right}
th:first-child,td:first-child{text-align:left}
.notes{opacity:.65;font-size:.85rem}
</style></head><body>
<h1>Ghostpanel — Benchmark Report</h1>
<p class=sub>__N__ benchmarks. Mechanical fidelity, quantified.</p>
__CARDS__
</body></html>"""
