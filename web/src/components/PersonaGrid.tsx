import { motion } from "framer-motion";
import type { RunState } from "../useRunStream";
import PersonaTile from "./PersonaTile";

export default function PersonaGrid({ state }: { state: RunState }) {
  const tiles = state.order
    .map((id) => state.personas[id])
    .filter((t) => t !== undefined);
  const total = tiles.length;
  const survived = tiles.filter((t) => t.status === "success").length;
  const dead = tiles.filter((t) => t.status === "dead").length;
  const finished = tiles.filter(
    (t) => t.status === "success" || t.status === "dead" || t.status === "error",
  ).length;
  const progress = total === 0 ? 0 : (finished / total) * 100;
  const running = state.status === "running";

  return (
    <section>
      <div className="flex flex-wrap items-end gap-6 mb-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-4">
            {running && (
              <motion.div
                className="w-2 h-2 rounded-full bg-emerald-500"
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
            )}
            <p className="text-sm font-mono text-muted-foreground">Live run</p>
          </div>
          <h2 className="text-3xl md:text-4xl font-light tracking-tight mb-2">
            {state.task || "…"}
          </h2>
          <p className="text-sm font-mono text-muted-foreground break-all">
            {state.targetUrl}
          </p>
        </div>
        <div className="ml-auto text-right">
          <p className="text-5xl md:text-6xl font-light tabular-nums" aria-live="polite">
            {survived}
            <span className="text-muted-foreground">/{total}</span>
          </p>
          <p className="text-xs text-muted-foreground mt-2">survived</p>
          {dead > 0 && (
            <p className="text-xs font-mono text-red-500 mt-1 tabular-nums" aria-live="polite">
              {dead} abandoned
            </p>
          )}
        </div>
      </div>

      <div
        className="h-1.5 rounded-full bg-border/50 overflow-hidden mb-8"
        role="progressbar"
        aria-valuenow={finished}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label="personas finished"
      >
        <div
          className="h-full rounded-full bg-foreground transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t, i) => (
          <PersonaTile key={t.persona.id} live={t} index={i} />
        ))}
      </div>
    </section>
  );
}
