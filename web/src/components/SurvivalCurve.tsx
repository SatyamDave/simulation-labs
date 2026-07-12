import { useState } from "react";
import type { PersonaOutcome, SurvivalPoint } from "../types";

/**
 * Outcome status palette — validated with the dataviz six-checks script on the
 * dark surface (#12141D): all PASS. Outcomes always carry a text label too,
 * so identity is never color-alone.
 */
export const OUTCOME_COLOR: Record<PersonaOutcome, string> = {
  success: "#2aa873",
  step_budget: "#b8842b",
  time_budget: "#b8842b",
  stuck: "#e05252",
  error: "#7681c6",
};

export const OUTCOME_LABEL: Record<PersonaOutcome, string> = {
  success: "survived",
  step_budget: "step budget",
  time_budget: "time budget",
  stuck: "stuck",
  error: "infra error",
};

interface Tip {
  x: number;
  y: number;
  point: SurvivalPoint;
}

export default function SurvivalCurve({ survival }: { survival: SurvivalPoint[] }) {
  const [tip, setTip] = useState<Tip | null>(null);
  if (survival.length === 0) return null;

  const maxSteps = Math.max(...survival.map((s) => s.steps_survived), 1);
  // deepest survivors first, completions on top
  const rows = [...survival].sort(
    (a, b) =>
      Number(b.completed) - Number(a.completed) ||
      b.steps_survived - a.steps_survived,
  );
  const legendOutcomes: PersonaOutcome[] = ["success", "step_budget", "stuck", "error"];
  const legendLabels: Record<string, string> = {
    success: "survived",
    step_budget: "budget exhausted (step/time)",
    stuck: "stuck / gave up",
    error: "infra error (excluded from stats)",
  };
  const present = new Set<PersonaOutcome>(
    rows.map((r) => (r.outcome === "time_budget" ? "step_budget" : r.outcome)),
  );

  return (
    <div className="survival">
      <div className="legend" aria-hidden="false">
        {legendOutcomes
          .filter((o) => present.has(o))
          .map((o) => (
            <span key={o}>
              <span
                className="swatch"
                style={{ background: OUTCOME_COLOR[o] }}
                aria-hidden="true"
              />
              {legendLabels[o]}
            </span>
          ))}
      </div>

      {rows.map((s) => (
        <div className="survival__row" key={s.persona_id}>
          <div className="survival__name" title={s.persona_id}>
            {s.persona_name || s.persona_id}
          </div>
          <div
            className="survival__track"
            onMouseMove={(e) =>
              setTip({ x: e.clientX + 14, y: e.clientY + 14, point: s })
            }
            onMouseLeave={() => setTip(null)}
          >
            <div
              className="survival__bar"
              style={{
                width: `${(s.steps_survived / maxSteps) * 100}%`,
                background: OUTCOME_COLOR[s.outcome],
              }}
            />
            <span className="survival__val">
              {s.steps_survived} steps{" "}
              <span className="outcome">
                · {s.completed ? "✓ survived" : OUTCOME_LABEL[s.outcome]}
              </span>
            </span>
          </div>
        </div>
      ))}

      <div className="survival__axis" aria-hidden="true">
        <div className="lbl">
          <span>0</span>
          <span>steps survived → {maxSteps}</span>
        </div>
      </div>

      {tip && (
        <div className="tip" style={{ left: tip.x, top: tip.y }} role="status">
          <strong>{tip.point.persona_name || tip.point.persona_id}</strong>
          <br />
          <span className="dim">
            {tip.point.steps_survived} steps · {OUTCOME_LABEL[tip.point.outcome]}
            {tip.point.completed ? " · completed the task" : ""}
          </span>
        </div>
      )}

      <details className="datatable">
        <summary>View as table</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">Persona</th>
              <th scope="col">Steps survived</th>
              <th scope="col">Outcome</th>
              <th scope="col">Completed</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.persona_id}>
                <td>{s.persona_name || s.persona_id}</td>
                <td>{s.steps_survived}</td>
                <td>{OUTCOME_LABEL[s.outcome]}</td>
                <td>{s.completed ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
