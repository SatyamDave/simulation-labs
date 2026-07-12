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
  // Hairline grid ticks at each step (skip if too dense to read).
  const ticks =
    maxSteps <= 24
      ? Array.from({ length: maxSteps }, (_, i) => ((i + 1) / maxSteps) * 100)
      : [25, 50, 75, 100];

  return (
    <figure className="p-5 rounded-lg border border-border bg-panel m-0">
      <figcaption className="mb-5">
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-1">
          Survival curve
        </p>
        <p className="text-sm text-muted-foreground">
          how far each persona got before finishing or giving up
        </p>
      </figcaption>

      <div
        className="flex flex-col gap-2.5"
        role="img"
        aria-label="Steps survived per persona"
      >
        {rows.map((r) => {
          const pct = (r.steps_survived / maxSteps) * 100;
          const color = OUTCOME_COLOR[r.outcome];
          return (
            <div
              className="grid grid-cols-[minmax(110px,170px)_1fr] gap-3 items-center max-sm:grid-cols-1 max-sm:gap-1"
              key={r.persona_id}
              title={`${r.persona_name || r.persona_id}: ${
                r.steps_survived
              } steps — ${OUTCOME_LABELS[r.outcome]}`}
            >
              <span className="font-mono text-xs truncate">
                {r.persona_name || r.persona_id}
              </span>
              <div className="relative min-h-6 flex items-center">
                {/* hairline grid ticks */}
                {ticks.map((t) => (
                  <span
                    key={t}
                    className="absolute top-0 bottom-0 w-px bg-hairline"
                    style={{ left: `${t}%` }}
                    aria-hidden="true"
                  />
                ))}
                <div
                  className="relative h-4 rounded-[2px] transition-all duration-700 min-w-1"
                  style={{ width: `${Math.max(pct, 2)}%`, background: color }}
                />
                <span
                  className={`relative font-mono text-[11px] whitespace-nowrap pl-2 tabular-nums ${OUTCOME_TEXT_CLASS[r.outcome]}`}
                >
                  {r.steps_survived} · {OUTCOME_LABELS[r.outcome].toLowerCase()}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-4 mt-5 pt-4 border-t border-hairline">
        {LEGEND_ORDER.filter((o) => present.has(o)).map((o) => (
          <span
            className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground"
            key={o}
          >
            <span
              className="w-2 h-2 rounded-[2px]"
              style={{ background: OUTCOME_COLOR[o] }}
            />
            {OUTCOME_LABELS[o]}
          </span>
        ))}
      </div>
    </figure>
  );
}
