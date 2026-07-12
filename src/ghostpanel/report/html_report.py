"""Render a RunReport into a standalone, self-contained HTML leave-behind.

`render_html(report)` returns the HTML string; `write_html_report(report,
artifact_dir)` writes it to ``<artifact_dir>/<run_id>/report.html`` and returns
the path. No external assets — everything (CSS, the survival bar chart as inline
SVG) is embedded so a PM/VC can open the file offline.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, select_autoescape

from ghostpanel_contracts import RunReport

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
        <p>
          {% if r.audio_path %}<a href="{{ r.audio_path }}">▶ audio (.wav)</a>{% endif %}
          {% if r.video_path %} · <a href="{{ r.video_path }}">🎬 video (.webm)</a>{% endif %}
        </p>
      </div>
    {% endfor %}
  </section>
</div>
</body>
</html>
"""
)


def render_html(report: RunReport) -> str:
    """Render a self-contained HTML page for a RunReport."""
    non_error = sum(1 for r in report.results if r.outcome.value != "error")
    successes = sum(1 for r in report.results if r.outcome.value == "success")
    steps = [s.steps_survived for s in report.survival] or [1]
    max_steps = max(steps) or 1
    # scale the longest bar to ~400px
    bar_unit = 400 / max_steps
    return _TEMPLATE.render(
        report=report,
        completion_pct=round(report.completion_rate * 100),
        successes=successes,
        non_error=non_error,
        max_bar=400,
        bar_unit=bar_unit,
        name_by_id={s.persona_id: s.persona_name for s in report.survival},
    )


def write_html_report(report: RunReport, artifact_dir: str | Path) -> str:
    """Render and write the report to ``<artifact_dir>/<run_id>/report.html``.

    Returns the absolute path to the written file.
    """
    out_dir = Path(artifact_dir) / report.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.html"
    path.write_text(render_html(report), encoding="utf-8")
    return str(path)
