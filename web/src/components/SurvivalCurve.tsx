import type { SurvivalPoint } from "../types";
import { OUTCOME_LABELS } from "../types";
import { OUTCOME_COLOR, OUTCOME_TEXT_CLASS } from "../theme";

interface Props {
  survival: SurvivalPoint[];
}

export function SurvivalCurve({ survival }: Props) {
  const rows = [...survival].sort(
    (a, b) => b.steps_survived - a.steps_survived
  );
  const maxSteps = Math.max(1, ...rows.map((r) => r.steps_survived));

  return (
    <div
      className="flex flex-col gap-3"
      role="img"
      aria-label="Steps survived per persona"
    >
      {rows.map((r) => {
        const pct = (r.steps_survived / maxSteps) * 100;
        return (
          <div
            className="grid grid-cols-[minmax(110px,160px)_1fr_auto] items-center gap-3 max-sm:grid-cols-[1fr_auto] max-sm:gap-x-3"
            key={r.persona_id}
            title={`${r.persona_name || r.persona_id}: ${
              r.steps_survived
            } steps — ${OUTCOME_LABELS[r.outcome]}`}
          >
            <span className="font-mono text-xs text-muted-foreground truncate max-sm:col-span-2">
              {r.persona_name || r.persona_id}
            </span>
            <div className="h-2 rounded-full bg-surface overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${Math.max(pct, 2)}%`,
                  background: OUTCOME_COLOR[r.outcome],
                }}
              />
            </div>
            <span
              className={`font-mono text-[11px] whitespace-nowrap tabular-nums ${OUTCOME_TEXT_CLASS[r.outcome]}`}
            >
              {r.steps_survived} · {OUTCOME_LABELS[r.outcome].toLowerCase()}
            </span>
          </div>
        );
      })}
    </div>
  );
}
