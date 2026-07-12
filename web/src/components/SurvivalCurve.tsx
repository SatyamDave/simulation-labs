import { useState } from "react";
import type { PersonaOutcome, SurvivalPoint } from "../types";

/**
 * Outcome palette per the design system: emerald-500 for success, red-500 for
 * every abandonment outcome, achromatic gray for infra errors (excluded from
 * survival stats). Outcomes always carry a text label — never color-alone.
 */
export const OUTCOME_COLOR: Record<PersonaOutcome, string> = {
  success: "#10b981", // emerald-500
  step_budget: "#ef4444", // red-500
  time_budget: "#ef4444",
  stuck: "#ef4444",
  error: "#737373", // achromatic — infra failure
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
  const legend: { key: string; color: string; label: string; show: boolean }[] = [
    {
      key: "success",
      color: OUTCOME_COLOR.success,
      label: "survived",
      show: rows.some((r) => r.outcome === "success"),
    },
    {
      key: "abandoned",
      color: OUTCOME_COLOR.stuck,
      label: "abandoned (budget / stuck)",
      show: rows.some(
        (r) =>
          r.outcome === "step_budget" ||
          r.outcome === "time_budget" ||
          r.outcome === "stuck",
      ),
    },
    {
      key: "error",
      color: OUTCOME_COLOR.error,
      label: "infra error (excluded from stats)",
      show: rows.some((r) => r.outcome === "error"),
    },
  ];

  return (
    <div className="p-6 rounded-2xl border border-border bg-background">
      <div className="flex flex-wrap gap-x-5 gap-y-1 mb-5 text-xs text-muted-foreground">
        {legend
          .filter((l) => l.show)
          .map((l) => (
            <span key={l.key} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ background: l.color }}
                aria-hidden="true"
              />
              {l.label}
            </span>
          ))}
      </div>

      {rows.map((s) => (
        <div
          className="grid grid-cols-[minmax(120px,190px)_1fr] gap-3 items-center py-1.5"
          key={s.persona_id}
        >
          <div
            className="text-sm text-right truncate"
            title={s.persona_id}
          >
            {s.persona_name || s.persona_id}
          </div>
          <div
            className="relative h-5 flex items-center"
            onMouseMove={(e) =>
              setTip({ x: e.clientX + 14, y: e.clientY + 14, point: s })
            }
            onMouseLeave={() => setTip(null)}
          >
            <div
              className="h-3 rounded-r-full min-w-[3px] transition-all duration-700"
              style={{
                width: `${(s.steps_survived / maxSteps) * 100}%`,
                background: OUTCOME_COLOR[s.outcome],
                opacity: s.outcome === "success" ? 1 : 0.75,
              }}
            />
            <span className="ml-2.5 text-xs text-muted-foreground tabular-nums whitespace-nowrap">
              {s.steps_survived} steps · {s.completed ? "survived" : OUTCOME_LABEL[s.outcome]}
            </span>
          </div>
        </div>
      ))}

      <div
        className="grid grid-cols-[minmax(120px,190px)_1fr] gap-3 mt-2 border-t border-border pt-2"
        aria-hidden="true"
      >
        <div className="col-start-2 flex justify-between text-xs text-muted-foreground tabular-nums">
          <span>0</span>
          <span>steps survived → {maxSteps}</span>
        </div>
      </div>

      {tip && (
        <div
          className="fixed z-40 pointer-events-none rounded-xl border border-border bg-popover text-popover-foreground px-3 py-2 text-xs shadow-lg shadow-foreground/5 max-w-70"
          style={{ left: tip.x, top: tip.y }}
          role="status"
        >
          <span className="font-medium">
            {tip.point.persona_name || tip.point.persona_id}
          </span>
          <br />
          <span className="text-muted-foreground tabular-nums">
            {tip.point.steps_survived} steps · {OUTCOME_LABEL[tip.point.outcome]}
            {tip.point.completed ? " · completed the task" : ""}
          </span>
        </div>
      )}

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground transition-colors">
          View as table
        </summary>
        <table className="mt-3 w-full border-collapse text-sm">
          <thead>
            <tr>
              <th scope="col" className="text-left px-2.5 py-1.5 border-b border-border text-xs font-mono text-muted-foreground uppercase tracking-wider font-medium">
                Persona
              </th>
              <th scope="col" className="text-left px-2.5 py-1.5 border-b border-border text-xs font-mono text-muted-foreground uppercase tracking-wider font-medium">
                Steps survived
              </th>
              <th scope="col" className="text-left px-2.5 py-1.5 border-b border-border text-xs font-mono text-muted-foreground uppercase tracking-wider font-medium">
                Outcome
              </th>
              <th scope="col" className="text-left px-2.5 py-1.5 border-b border-border text-xs font-mono text-muted-foreground uppercase tracking-wider font-medium">
                Completed
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.persona_id}>
                <td className="px-2.5 py-1.5 border-b border-border text-muted-foreground">
                  {s.persona_name || s.persona_id}
                </td>
                <td className="px-2.5 py-1.5 border-b border-border text-muted-foreground tabular-nums">
                  {s.steps_survived}
                </td>
                <td className="px-2.5 py-1.5 border-b border-border text-muted-foreground">
                  {OUTCOME_LABEL[s.outcome]}
                </td>
                <td className="px-2.5 py-1.5 border-b border-border text-muted-foreground">
                  {s.completed ? "yes" : "no"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
