import { motion } from "framer-motion";
import type { LiveRunState, TileStatus, Viewport } from "../types";
import { tallies } from "../runReducer";
import { PersonaTile } from "./PersonaTile";
import { VitalLine } from "./VitalLine";

interface Props {
  state: LiveRunState;
  coordSpace?: Viewport;
  onSeeReport?: () => void;
  reportReady?: boolean;
}

function Reading({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "ok" | "fail" | "live";
}) {
  const cls =
    tone === "ok"
      ? "text-ok"
      : tone === "fail"
        ? "text-fail"
        : tone === "live"
          ? "text-live"
          : "text-foreground";
  return (
    <span className="whitespace-nowrap">
      <span className="text-muted-foreground">{label} </span>
      <span className={`${cls} font-medium`}>{value}</span>
    </span>
  );
}

export function PersonaGrid({
  state,
  coordSpace,
  onSeeReport,
  reportReady,
}: Props) {
  const t = tallies(state);
  const finished = state.status === "finished";

  // Aggregate vital sign for the whole run: amber while anything is alive,
  // emerald once finished with survivors, flatline if everyone died.
  const aggStatus: TileStatus =
    t.total === 0
      ? "pending"
      : finished || t.done === t.total
        ? t.survived > 0
          ? "success"
          : "abandoned"
        : "running";

  return (
    <section className="flex flex-col gap-6">
      {/* Telemetry strip — one instrument bar, not four boxes */}
      <div className="rounded-lg border border-border bg-panel overflow-hidden">
        <div className="flex items-center gap-x-5 gap-y-1 flex-wrap px-4 py-2.5 font-mono text-xs uppercase tracking-wider tabular-nums border-b border-hairline">
          <Reading label="survived" value={t.survived} tone="ok" />
          <span className="text-hairline" aria-hidden="true">
            ·
          </span>
          <Reading label="abandoned" value={t.dead} tone="fail" />
          <span className="text-hairline" aria-hidden="true">
            ·
          </span>
          <Reading
            label="running"
            value={t.running}
            tone={t.running > 0 ? "live" : undefined}
          />
          <span className="ml-auto text-muted-foreground">
            <span className="text-foreground font-medium">
              {t.done}/{t.total}
            </span>{" "}
            finished
          </span>
        </div>
        <VitalLine status={aggStatus} height={28} />
        <div className="px-4 py-2 font-mono text-xs text-muted-foreground border-t border-hairline flex flex-wrap gap-x-4 gap-y-0.5 min-w-0">
          <span className="truncate">
            <span className="uppercase tracking-wider text-[10px]">task</span>{" "}
            <span className="text-foreground">{state.task || "—"}</span>
          </span>
          <span className="truncate">
            <span className="uppercase tracking-wider text-[10px]">target</span>{" "}
            {state.targetUrl || "—"}
          </span>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-5">
        {state.order.map((id, i) => {
          const live = state.personas[id];
          if (!live) return null;
          return (
            <PersonaTile
              key={id}
              live={live}
              index={i}
              coordSpace={coordSpace}
            />
          );
        })}
      </div>

      {reportReady && onSeeReport && (
        <div className="flex justify-center pt-4">
          <motion.button
            className="px-6 py-3 rounded-md bg-foreground text-background font-mono text-sm uppercase tracking-wider"
            whileTap={{ scale: 0.98 }}
            onClick={onSeeReport}
          >
            View the report →
          </motion.button>
        </div>
      )}
    </section>
  );
}
