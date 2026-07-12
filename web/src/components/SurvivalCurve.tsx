import type { PersonaOutcome, SurvivalPoint } from "../types";
import { OUTCOME_LABELS } from "../types";
import { OUTCOME_COLOR, OUTCOME_TEXT_CLASS } from "../theme";

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
    <figure className="p-6 rounded-2xl border border-border bg-background m-0">
      <figcaption className="mb-6">
        <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">
          Survival curve
        </p>
        <p className="text-sm text-muted-foreground">
          how far each persona got before finishing or giving up
        </p>
      </figcaption>

      <div
        className="flex flex-col gap-3"
        role="img"
        aria-label="Steps survived per persona"
      >
        {rows.map((r) => {
          const pct = (r.steps_survived / maxSteps) * 100;
          const color = OUTCOME_COLOR[r.outcome];
          return (
            <div
              className="grid grid-cols-[minmax(120px,190px)_1fr] gap-3 items-center max-sm:grid-cols-1 max-sm:gap-1"
              key={r.persona_id}
              title={`${r.persona_name || r.persona_id}: ${
                r.steps_survived
              } steps — ${OUTCOME_LABELS[r.outcome]}`}
            >
              <div className="flex items-center gap-2 text-sm font-medium truncate">
                {r.completed ? (
                  <svg
                    className="w-4 h-4 text-emerald-500 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-label="Completed"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                ) : (
                  <svg
                    className="w-4 h-4 text-red-500 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-label="Abandoned"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                )}
                <span className="truncate">{r.persona_name || r.persona_id}</span>
              </div>
              <div className="relative flex items-center gap-3 rounded-lg bg-muted/50 min-h-7">
                <div
                  className="h-5 rounded-md flex items-center justify-end px-2 min-w-6 transition-all duration-700"
                  style={{ width: `${Math.max(pct, 4)}%`, background: color }}
                >
                  <span className="text-xs font-medium text-background tabular-nums">
                    {r.steps_survived}
                  </span>
                </div>
                <span
                  className={`text-xs font-medium whitespace-nowrap ${OUTCOME_TEXT_CLASS[r.outcome]}`}
                >
                  {OUTCOME_LABELS[r.outcome]}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-4 mt-6 pt-4 border-t border-border/40">
        {LEGEND_ORDER.filter((o) => present.has(o)).map((o) => (
          <span
            className="inline-flex items-center gap-2 text-xs text-muted-foreground"
            key={o}
          >
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: OUTCOME_COLOR[o] }}
            />
            {OUTCOME_LABELS[o]}
          </span>
        ))}
      </div>
    </figure>
  );
}
