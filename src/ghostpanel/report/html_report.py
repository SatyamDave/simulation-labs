"""Standalone HTML artifact for a RunReport (the leave-behind a PM/VC keeps).

`render_html(report)` -> self-contained page: headline completion rate,
survival table, inline-SVG survival bar chart, abandonment heatmap points,
artifact links (.webm / .wav) and each persona's exit-interview transcript.
`write_html(report, artifact_dir)` writes it to
<artifact_dir>/<run_id>/report.html.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment

from ghostpanel_contracts import PersonaOutcome, RunReport

_OUTCOME_LABELS = {
    PersonaOutcome.SUCCESS: "completed",
    PersonaOutcome.STEP_BUDGET: "ran out of steps",
    PersonaOutcome.TIME_BUDGET: "ran out of time",
    PersonaOutcome.STUCK: "got stuck",
    PersonaOutcome.ERROR: "infra error",
}

# Chart geometry (SVG user units).
_BAR_H = 22
_BAR_GAP = 10
_LABEL_W = 220
_CHART_W = 560

_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghostpanel — {{ report.run_id }}</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
         max-width: 880px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
  .headline { font-size: 3rem; font-weight: 700; margin: .2em 0; }
  .meta { color: #777; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #8884; }
  .ok { color: #1a7f37; font-weight: 600; } .fail { color: #c62828; font-weight: 600; }
  .err { color: #999; }
  blockquote { border-left: 3px solid #8886; margin: .4rem 0 1rem; padding: .2rem .8rem;
               font-style: italic; }
  code { font-size: .85em; }
  a { color: inherit; }
</style>
</head>
<body>
<h1>Ghostpanel run report</h1>
<p class="meta">
  Run <code>{{ report.run_id }}</code> &middot; target <a href="{{ report.target_url }}">{{ report.target_url }}</a><br>
  Task: &ldquo;{{ report.task }}&rdquo; &middot; generated {{ report.generated_at }}
  &middot; contracts v{{ report.contract_version }}
</p>

<div class="headline">{{ "%.0f" | format(report.completion_rate * 100) }}%</div>
<p>of personas completed the task ({{ n_success }}/{{ n_counted }} counted; infra errors excluded).</p>

<h2>Survival — steps survived per persona</h2>
<svg viewBox="0 0 {{ svg_w }} {{ svg_h }}" width="100%" role="img"
     aria-label="Survival bar chart">
  {%- for b in bars %}
  <text x="{{ label_w - 8 }}" y="{{ b.y + 15 }}" text-anchor="end"
        font-size="12" fill="currentColor">{{ b.name }}</text>
  <rect x="{{ label_w }}" y="{{ b.y }}" width="{{ b.w }}" height="{{ bar_h }}"
        rx="3" fill="{{ '#2e9e5b' if b.completed else '#d64545' }}"></rect>
  <text x="{{ label_w + b.w + 6 }}" y="{{ b.y + 15 }}" font-size="12"
        fill="currentColor">{{ b.steps }} steps &mdash; {{ b.outcome }}</text>
  {%- endfor %}
</svg>

<h2>Survival table</h2>
<table>
  <tr><th>Persona</th><th>Outcome</th><th>Steps survived</th><th>Completed</th></tr>
  {%- for s in report.survival %}
  <tr>
    <td>{{ s.persona_name or s.persona_id }}</td>
    <td class="{{ 'ok' if s.completed else ('err' if s.outcome.value == 'error' else 'fail') }}">
        {{ outcome_labels[s.outcome] }}</td>
    <td>{{ s.steps_survived }}</td>
    <td>{{ "yes" if s.completed else "no" }}</td>
  </tr>
  {%- endfor %}
</table>

<h2>Abandonment heatmap points</h2>
{%- if report.heatmap_points %}
<table>
  <tr><th>x</th><th>y</th><th>weight</th><th>persona</th></tr>
  {%- for p in report.heatmap_points %}
  <tr><td>{{ p.x }}</td><td>{{ p.y }}</td><td>{{ p.weight }}</td><td>{{ p.persona_id }}</td></tr>
  {%- endfor %}
</table>
{%- else %}
<p class="meta">No abandonments recorded.</p>
{%- endif %}

<h2>Exit interviews &amp; receipts</h2>
{%- for r in report.results %}
<h3>{{ names.get(r.persona_id, r.persona_id) }}
    <span class="{{ 'ok' if r.outcome.value == 'success' else 'fail' }}">
      ({{ outcome_labels[r.outcome] }}{{ ", " ~ ("%.1f" | format(r.duration_s)) ~ "s" if r.duration_s }})
    </span></h3>
{%- if r.failure_reason %}<p class="meta">{{ r.failure_reason }}</p>{%- endif %}
{%- if r.transcript %}<blockquote>{{ r.transcript }}</blockquote>{%- endif %}
<p class="meta">
  {%- if r.video_path %} <a href="{{ r.video_path }}">video receipt (.webm)</a>{%- endif %}
  {%- if r.audio_path %} &middot; <a href="{{ r.audio_path }}">exit interview (.wav)</a>{%- endif %}
</p>
{%- endfor %}
</body>
</html>
"""

_env = Environment(autoescape=True)
_template = _env.from_string(_TEMPLATE)


def render_html(report: RunReport) -> str:
    """Render a RunReport to a standalone, self-contained HTML page."""
    max_steps = max((s.steps_survived for s in report.survival), default=0) or 1
    plot_w = _CHART_W - _LABEL_W - 140  # room for the trailing value label
    bars = [
        {
            "name": s.persona_name or s.persona_id,
            "y": i * (_BAR_H + _BAR_GAP),
            "w": max(2, round(s.steps_survived / max_steps * plot_w)),
            "steps": s.steps_survived,
            "completed": s.completed,
            "outcome": _OUTCOME_LABELS[s.outcome],
        }
        for i, s in enumerate(report.survival)
    ]
    names = {s.persona_id: s.persona_name for s in report.survival}
    return _template.render(
        report=report,
        bars=bars,
        names=names,
        outcome_labels=_OUTCOME_LABELS,
        n_success=sum(1 for s in report.survival if s.completed),
        n_counted=sum(1 for s in report.survival if s.outcome != PersonaOutcome.ERROR),
        svg_w=_CHART_W,
        svg_h=max(1, len(bars)) * (_BAR_H + _BAR_GAP),
        bar_h=_BAR_H,
        label_w=_LABEL_W,
    )


def write_html(report: RunReport, artifact_dir: str | Path) -> Path:
    """Write the rendered report to <artifact_dir>/<run_id>/report.html."""
    out_dir = Path(artifact_dir) / report.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.html"
    out_path.write_text(render_html(report), encoding="utf-8")
    return out_path
