import type { PersonaOutcome, SurvivalPoint } from "../types";
import { OUTCOME_LABELS } from "../types";
import { OUTCOME_COLOR } from "../theme";

interface Props {
  survival: SurvivalPoint[];
}

const LEGEND_ORDER: PersonaOutcome[] = [
  "success",
  "step_budget",
  "time_budget",
  "stuck",
  "error",
];

export function SurvivalCurve({ survival }: Props) {
  // Exclude infra errors from the visual per the contract note, but keep them
  // if that's all we have.
  const rows = [...survival].sort((a, b) => b.steps_survived - a.steps_survived);
  const maxSteps = Math.max(1, ...rows.map((r) => r.steps_survived));
  const present = new Set(rows.map((r) => r.outcome));

  return (
    <figure className="chart">
      <figcaption className="chart__title">
        Per-persona outcome
        <span className="chart__sub">
          how far each persona got before finishing or giving up
        </span>
      </figcaption>

      <div className="survival" role="img" aria-label="Steps survived per persona">
        {rows.map((r) => {
          const pct = (r.steps_survived / maxSteps) * 100;
          const color = OUTCOME_COLOR[r.outcome];
          return (
            <div
              className="survival__row"
              key={r.persona_id}
              title={`${r.persona_name || r.persona_id}: ${
                r.steps_survived
              } steps — ${OUTCOME_LABELS[r.outcome]}`}
            >
              <div className="survival__name">
                {r.completed ? (
                  <span className="survival__crown" title="Completed">
                    ✓
                  </span>
                ) : (
                  <span className="survival__skull" title="Abandoned">
                    ✕
                  </span>
                )}
                {r.persona_name || r.persona_id}
              </div>
              <div className="survival__track">
                <div
                  className="survival__fill"
                  style={{
                    width: `${Math.max(pct, 4)}%`,
                    background: color,
                    boxShadow: `0 0 18px ${color}66`,
                  }}
                >
                  <span className="survival__steps">{r.steps_survived}</span>
                </div>
                <span className="survival__outcome" style={{ color }}>
                  {OUTCOME_LABELS[r.outcome]}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="legend">
        {LEGEND_ORDER.filter((o) => present.has(o)).map((o) => (
          <span className="legend__item" key={o}>
            <span
              className="legend__swatch"
              style={{ background: OUTCOME_COLOR[o] }}
            />
            {OUTCOME_LABELS[o]}
          </span>
        ))}
      </div>
    </figure>
  );
}
