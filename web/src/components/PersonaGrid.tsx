import { motion } from "framer-motion";
import type { LiveRunState, Viewport } from "../types";
import { tallies } from "../runReducer";
import { PersonaTile } from "./PersonaTile";

interface Props {
  state: LiveRunState;
  coordSpace?: Viewport;
  onSeeReport?: () => void;
  reportReady?: boolean;
}

function Stat({
  value,
  label,
  tone,
}: {
  value: string | number;
  label: string;
  tone?: "good" | "bad";
}) {
  return (
    <div className="px-5 py-3 rounded-2xl border border-border bg-background text-center min-w-24">
      <p
        className={`text-3xl font-light tabular-nums leading-none ${
          tone === "good"
            ? "text-emerald-500"
            : tone === "bad"
              ? "text-red-500"
              : ""
        }`}
      >
        {value}
      </p>
      <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mt-2">
        {label}
      </p>
    </div>
  );
}

export function PersonaGrid({
  state,
  coordSpace,
  onSeeReport,
  reportReady,
}: Props) {
  const t = tallies(state);
  const progress = t.total ? Math.round((t.done / t.total) * 100) : 0;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex justify-between items-end gap-6 flex-wrap">
        <div className="min-w-0">
          <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-2">
            Task
          </p>
          <h2 className="text-2xl md:text-3xl font-light tracking-tight">
            {state.task || "—"}
          </h2>
          <p className="text-sm font-mono text-muted-foreground mt-2 break-all">
            {state.targetUrl}
          </p>
        </div>

        <div className="flex gap-6 flex-wrap">
          <Stat value={t.survived} label="survived" tone="good" />
          <Stat value={t.dead} label="abandoned" tone="bad" />
          <Stat
            value={t.running > 0 ? t.running : "—"}
            label={t.running > 0 ? "still trying" : "all done"}
          />
          <Stat value={`${t.done}/${t.total}`} label="finished" />
        </div>
      </div>

      <div className="h-1.5 rounded-full bg-border/50 overflow-hidden">
        <div
          className="h-full rounded-full bg-foreground transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-6">
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
        <div className="flex justify-center pt-6">
          <motion.button
            className="px-8 py-4 bg-foreground text-background rounded-full font-medium text-lg flex items-center gap-2"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onSeeReport}
          >
            View the report
            <motion.span
              animate={{ x: [0, 5, 0] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              →
            </motion.span>
          </motion.button>
        </div>
      )}
    </section>
  );
}
