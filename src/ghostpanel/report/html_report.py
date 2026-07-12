"""Render a RunReport into a standalone, self-contained HTML leave-behind.

`render_html(report)` returns the HTML string; `write_html_report(report,
artifact_dir)` writes it to ``<artifact_dir>/<run_id>/report.html`` and returns
the path. No external assets — everything (CSS, the survival bar chart as inline
SVG) is embedded so a PM/VC can open the file offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, select_autoescape

from ghostpanel_contracts import PersonaConfig, RunReport

from .insights import build_insights

_env = Environment(autoescape=select_autoescape(["html", "xml"]))

_TEMPLATE = _env.from_string(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghostpanel report — {{ report.run_id }}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; padding: 2rem; line-height: 1.5; }
  .wrap { max-width: 960px; margin: 0 auto; }
  h1 { margin: 0 0 .25rem; font-size: 1.6rem; }
  .sub { opacity: .7; font-size: .9rem; margin-bottom: 1.5rem; }
  .headline { font-size: 3rem; font-weight: 800; }
  .headline small { font-size: 1rem; font-weight: 400; opacity: .7; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem; }
  th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid rgba(128,128,128,.3); }
  th { font-weight: 600; }
  .ok { color: #1a9c4c; font-weight: 600; }
  .fail { color: #c0392b; font-weight: 600; }
  .card { border: 1px solid rgba(128,128,128,.25); border-radius: 10px; padding: 1rem 1.2rem;
          margin: 1rem 0; }
  .card h3 { margin: 0 0 .25rem; }
  .quote { font-style: italic; opacity: .9; }
  .bar-row { display: flex; align-items: center; gap: .5rem; margin: .2rem 0; }
  .bar-label { width: 180px; font-size: .82rem; text-align: right; }
  .tiles { display: flex; flex-wrap: wrap; gap: .8rem; margin: 1rem 0; }
  .tile { border: 1px solid rgba(128,128,128,.25); border-radius: 10px;
          padding: .8rem 1rem; min-width: 120px; }
  .tile-num { font-size: 1.5rem; font-weight: 800; }
  .tile-label { font-size: .76rem; opacity: .7; }
  svg .axis { font-size: 11px; fill: currentColor; opacity: .6; }
  a { color: #3b82f6; }
  .mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .82rem; }
  section { margin: 2rem 0; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Ghostpanel — behavioral survival report</h1>
  <div class="sub">
    Task: <strong>{{ report.task }}</strong><br>
    Target: <span class="mono">{{ report.target_url }}</span><br>
    Run <span class="mono">{{ report.run_id }}</span>
    · generated {{ report.generated_at }}
    · contract {{ report.contract_version }}
  </div>

  <div class="headline">{{ completion_pct }}%
    <small>of non-error personas completed the task
      ({{ successes }}/{{ non_error }})</small>
  </div>

  {% if insights %}
  <section>
    <h2>Ghostpanel score</h2>
    <div class="headline">{{ insights.ghostpanel_score }}<small> / 100
      — composite survival score (partial credit for steps survived;
      infra errors excluded)</small>
    </div>
    {% if insights.agent_readiness %}
    <div class="card">
      <h3>Agent readiness
        <span class="{{ 'ok' if insights.agent_readiness.outcome == 'success' else 'fail' }}">
          · {{ insights.agent_readiness.score }}/100</span></h3>
      <p>{{ insights.agent_readiness.note }}
        <span class="mono">({{ insights.agent_readiness.outcome }},
          {{ insights.agent_readiness.steps }} steps)</span></p>
    </div>
    {% endif %}
    {% if insights.summary %}<p>{{ insights.summary }}</p>{% endif %}
  </section>

  {% if insights.wcag_findings %}
  <section>
    <h2>Accessibility risk evidence — WCAG 2.2 / EN 301 549</h2>
    <div class="sub">Behavioral evidence of risk from degraded-perception traces,
      not automated conformance verdicts.</div>
    <table>
      <thead><tr><th>Criterion</th><th>Level</th><th>EN 301 549</th>
        <th>Persona</th><th>Evidence</th></tr></thead>
      <tbody>
      {% for f in insights.wcag_findings %}
        <tr>
          <td class="mono">{{ f.criterion }} {{ f.name }}</td>
          <td>{{ f.level }}</td>
          <td class="mono">{{ f.standard_ref }}</td>
          <td>{{ f.persona_name or f.persona_id }}</td>
          <td>{{ f.evidence }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>
  {% endif %}
  {% endif %}

  {% if run_stats or curve %}
  <section>
    <h2>Run statistics</h2>
    {% if run_stats %}
    <div class="tiles">
      {% if insights %}
      <div class="tile"><div class="tile-num">{{ insights.ghostpanel_score }}</div>
        <div class="tile-label">Ghostpanel score</div></div>
      {% endif %}
      <div class="tile"><div class="tile-num">{{ completion_pct }}%</div>
        <div class="tile-label">completion</div></div>
      <div class="tile"><div class="tile-num">{{ run_stats.avg_latency_ms }} ms</div>
        <div class="tile-label">avg Holo latency</div></div>
      <div class="tile"><div class="tile-num">{{ run_stats.p95_latency_ms }} ms</div>
        <div class="tile-label">p95 Holo latency</div></div>
      <div class="tile"><div class="tile-num">{{ run_stats.total_steps }}</div>
        <div class="tile-label">total steps</div></div>
      <div class="tile"><div class="tile-num">{{ run_stats.blocked_actions }}</div>
        <div class="tile-label">policy-blocked actions</div></div>
    </div>
    {% endif %}

    {% if curve %}
    <h3>Survival curve</h3>
    <div class="sub">personas alive vs step (non-error personas)</div>
    <svg width="{{ curve.width }}" height="{{ curve.height }}" role="img"
         aria-label="Stepped survival curve: personas alive by step">
      <line x1="{{ curve.x0 }}" y1="{{ curve.y0 }}" x2="{{ curve.x1 }}"
            y2="{{ curve.y0 }}" stroke="rgba(128,128,128,.5)"/>
      <line x1="{{ curve.x0 }}" y1="{{ curve.y0 }}" x2="{{ curve.x0 }}"
            y2="{{ curve.y1 }}" stroke="rgba(128,128,128,.5)"/>
      <path d="{{ curve.path }}" fill="none" stroke="#3b82f6"
            stroke-width="2" stroke-linejoin="round"/>
      <text class="axis" x="{{ curve.x0 }}" y="{{ curve.y0 + 14 }}">0</text>
      <text class="axis" x="{{ curve.x1 }}" y="{{ curve.y0 + 14 }}"
            text-anchor="end">{{ curve.max_step }} steps</text>
      <text class="axis" x="{{ curve.x0 - 6 }}" y="{{ curve.y1 + 4 }}"
            text-anchor="end">{{ curve.max_alive }}</text>
      <text class="axis" x="{{ curve.x0 - 6 }}" y="{{ curve.y0 + 4 }}"
            text-anchor="end">0</text>
    </svg>
    {% endif %}

    {% if persona_stats %}
    <h3>Per-persona breakdown</h3>
    <table>
      <thead><tr><th>Persona</th><th>Outcome</th><th>Steps</th><th>Duration (s)</th>
        <th>Avg latency (ms)</th><th>Blocked</th><th>Max repeat</th>
        <th>Perturbations</th></tr></thead>
      <tbody>
      {% for p in persona_stats %}
        <tr>
          <td>{{ p.persona_name or p.persona_id }}</td>
          <td class="{{ 'ok' if p.outcome == 'success' else 'fail' }}">{{ p.outcome }}</td>
          <td>{{ p.steps }}</td>
          <td>{{ p.duration_s }}</td>
          <td>{{ p.avg_latency_ms }}</td>
          <td>{{ p.blocked_actions }}</td>
          <td>{{ p.max_repeated_action }}</td>
          <td class="mono">{{ p.perturbations | join(', ') or 'baseline' }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    {% endif %}

    {% if action_bars %}
    <h3>Actions by type</h3>
    <div>
    {% for a in action_bars %}
      <div class="bar-row">
        <div class="bar-label mono">{{ a.type }}</div>
        <svg width="310" height="14" role="img"
             aria-label="{{ a.count }} {{ a.type }} actions">
          <rect x="0" y="0" height="14" rx="3" width="{{ a.px }}"
                fill="#3b82f6"></rect>
        </svg>
        <span class="mono">{{ a.count }}</span>
      </div>
    {% endfor %}
    </div>
    {% endif %}
  </section>
  {% endif %}

  <section>
    <h2>Survival</h2>
    <div>
    {% for s in report.survival %}
      <div class="bar-row">
        <div class="bar-label">{{ s.persona_name or s.persona_id }}</div>
        <svg width="{{ max_bar }}" height="18" role="img"
             aria-label="{{ s.steps_survived }} steps survived">
          <rect x="0" y="0" height="18" rx="3"
                width="{{ (s.steps_survived * bar_unit) | round(0, 'floor') | int }}"
                fill="{{ '#1a9c4c' if s.completed else '#c0392b' }}"></rect>
        </svg>
        <span class="mono">{{ s.steps_survived }} steps
          · {{ '✓' if s.completed else s.outcome.value }}</span>
      </div>
    {% endfor %}
    </div>

    <table>
      <thead><tr><th>Persona</th><th>Outcome</th><th>Steps survived</th><th>Completed</th></tr></thead>
      <tbody>
      {% for s in report.survival %}
        <tr>
          <td>{{ s.persona_name or s.persona_id }}</td>
          <td>{{ s.outcome.value }}</td>
          <td>{{ s.steps_survived }}</td>
          <td class="{{ 'ok' if s.completed else 'fail' }}">
            {{ 'yes' if s.completed else 'no' }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>

  <section>
    <h2>Abandonment heatmap points</h2>
    {% if report.heatmap_points %}
    <table>
      <thead><tr><th>Persona</th><th>x</th><th>y</th><th>weight</th></tr></thead>
      <tbody>
      {% for h in report.heatmap_points %}
        <tr><td>{{ h.persona_id }}</td><td>{{ h.x }}</td><td>{{ h.y }}</td>
            <td>{{ h.weight }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p>No abandonment points (everyone succeeded).</p>
    {% endif %}
  </section>

  <section>
    <h2>Exit interviews</h2>
    {% for r in report.results %}
      <div class="card">
        <h3>{{ name_by_id.get(r.persona_id, r.persona_id) }}
          <span class="{{ 'ok' if r.outcome.value == 'success' else 'fail' }}">
            · {{ r.outcome.value }}</span></h3>
        {% if r.transcript %}
          <p class="quote">&ldquo;{{ r.transcript }}&rdquo;</p>
        {% else %}
          <p class="quote">(no transcript)</p>
        {% endif %}
        {% if r.failure_reason %}
          <p class="mono">reason: {{ r.failure_reason }}</p>
        {% endif %}
        {% set m = media.get(r.persona_id, {}) %}
        <p>
          {% if m.audio %}<a href="{{ m.audio }}">▶ audio (.wav)</a>{% endif %}
          {% if m.video %} · <a href="{{ m.video }}">🎬 video (.webm)</a>{% endif %}
        </p>
      </div>
    {% endfor %}
  </section>
</div>
</body>
</html>
"""
)


def _media_href(path: Optional[str], run_dir: Optional[Path]) -> Optional[str]:
    """Href for a media file next to report.html.

    The report is written to ``<artifact_dir>/<run_id>/report.html`` and served
    at ``/artifacts/<run_id>/report.html``; the .webm/.wav receipts live in the
    same run directory, so an absolute filesystem path would 404 when served.
    Use the bare basename (a relative sibling href). Safe fallback: if the file
    verifiably lives OUTSIDE the run dir, keep the original path rather than
    emit a broken sibling link.
    """
    if not path:
        return None
    p = Path(path)
    # A relative path can't be located reliably (it depends on cwd) — use the
    # sibling-basename convention. Only a verifiably-elsewhere absolute path
    # keeps its original value.
    if p.is_absolute() and run_dir is not None:
        try:
            if p.resolve().parent != Path(run_dir).resolve():
                return path
        except OSError:
            return path
    return p.name


def _survival_curve(
    series: list[dict], width: int = 640, height: int = 170, pad: int = 30
) -> Optional[dict]:
    """Geometry for the inline-SVG stepped (step-after) survival curve.
    ``series`` is the insights ``survival_series``; None when there is nothing
    worth plotting (fewer than two points)."""
    if len(series) < 2:
        return None
    max_step = max(p["step"] for p in series) or 1
    max_alive = max(p["alive"] for p in series) or 1

    def sx(step: int) -> float:
        return pad + step / max_step * (width - 2 * pad)

    def sy(alive: int) -> float:
        return height - pad - alive / max_alive * (height - 2 * pad)

    path = f"M{sx(series[0]['step']):.1f} {sy(series[0]['alive']):.1f}"
    for point in series[1:]:
        # step-after: hold the previous value until the new step, then drop
        path += f" H{sx(point['step']):.1f} V{sy(point['alive']):.1f}"
    return {
        "width": width,
        "height": height,
        "path": path,
        "max_step": max_step,
        "max_alive": max_alive,
        "x0": pad,
        "x1": width - pad,
        "y0": height - pad,
        "y1": pad,
    }


def _action_bars(run_stats: Optional[dict], max_px: int = 300) -> list[dict]:
    """Actions-by-type rows (type, count, bar width) sorted by count desc."""
    by_type = (run_stats or {}).get("actions_by_type") or {}
    if not by_type:
        return []
    peak = max(by_type.values())
    return [
        {"type": t, "count": c, "px": round(c / peak * max_px)}
        for t, c in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _load_run_personas(report: RunReport) -> list[PersonaConfig]:
    """Best-effort persona configs for this run's ids from personas/*.json, so
    reports written without an explicit ``personas=`` (today's server call) still
    get the insights section. Any hiccup degrades to no insights, never a crash."""
    try:
        from ghostpanel.engine.personas import load_personas

        ids = [s.persona_id for s in report.survival] or [
            r.persona_id for r in report.results
        ]
        return load_personas(ids)  # unknown ids are silently skipped
    except Exception:  # noqa: BLE001 - insights are additive, never required
        return []


def render_html(
    report: RunReport,
    insights: Optional[dict] = None,
    personas: Optional[list[PersonaConfig]] = None,
    run_dir: Optional[str | Path] = None,
) -> str:
    """Render a self-contained HTML page for a RunReport.

    ``insights`` (the `build_insights` payload) is optional: when omitted it is
    computed from ``personas`` (falling back to the on-disk persona roster); if
    no personas can be resolved the insights section is simply omitted.
    ``run_dir`` is the directory report.html will live in, used to relativize
    media hrefs.
    """
    if insights is None:
        resolved = personas if personas is not None else _load_run_personas(report)
        if resolved:
            insights = build_insights(report, resolved)
    run_dir_path = Path(run_dir) if run_dir is not None else None
    media = {
        r.persona_id: {
            "audio": _media_href(r.audio_path, run_dir_path),
            "video": _media_href(r.video_path, run_dir_path),
        }
        for r in report.results
    }
    non_error = sum(1 for r in report.results if r.outcome.value != "error")
    successes = sum(1 for r in report.results if r.outcome.value == "success")
    steps = [s.steps_survived for s in report.survival] or [1]
    max_steps = max(steps) or 1
    # scale the longest bar to ~400px
    bar_unit = 400 / max_steps
    # New stats keys are additive: older insights payloads simply lack them,
    # and every derived section degrades to "not rendered".
    stats = (insights or {}).get("stats") or {}
    run_stats = stats.get("run")
    return _TEMPLATE.render(
        report=report,
        insights=insights,
        run_stats=run_stats,
        persona_stats=stats.get("personas") or [],
        curve=_survival_curve((insights or {}).get("survival_series") or []),
        action_bars=_action_bars(run_stats),
        media=media,
        completion_pct=round(report.completion_rate * 100),
        successes=successes,
        non_error=non_error,
        max_bar=400,
        bar_unit=bar_unit,
        name_by_id={s.persona_id: s.persona_name for s in report.survival},
    )


def write_html_report(
    report: RunReport,
    artifact_dir: str | Path,
    insights: Optional[dict] = None,
    personas: Optional[list[PersonaConfig]] = None,
) -> str:
    """Render and write the report to ``<artifact_dir>/<run_id>/report.html``.

    Returns the absolute path to the written file.
    """
    out_dir = Path(artifact_dir) / report.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.html"
    path.write_text(
        render_html(report, insights=insights, personas=personas, run_dir=out_dir),
        encoding="utf-8",
    )
    return str(path)
