import { motion } from "framer-motion";
import type { LiveRunState, Viewport } from "../types";
import { tallies } from "../runReducer";
import { PersonaTile } from "./PersonaTile";

interface Props {
  state: LiveRunState;
  coordSpace?: Viewport;
  // Static target screenshot shown behind tiles when no live thumb is streamed
  // (simulated runs pass the target page mock).
  backdrop?: string;
  onSeeReport?: () => void;
  reportReady?: boolean;
}

function Dot({
  tone,
  pulse,
}: {
  tone: "ok" | "fail" | "live" | "idle";
  pulse?: boolean;
}) {
  const cls =
    tone === "ok"
      ? "bg-ok"
      : tone === "fail"
        ? "bg-fail"
        : tone === "live"
          ? "bg-live"
          : "bg-idle/40";
  if (pulse) {
    return (
      <motion.span
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${cls}`}
        animate={{ opacity: [1, 0.35, 1] }}
        transition={{ duration: 1.6, repeat: Infinity }}
        aria-hidden="true"
      />
    );
  }
  return (
    <span
      className={`w-1.5 h-1.5 rounded-full shrink-0 ${cls}`}
      aria-hidden="true"
    />
  );
}

export function PersonaGrid({
  state,
  coordSpace,
  backdrop,
  onSeeReport,
  reportReady,
}: Props) {
  const t = tallies(state);

  return (
    <section className="flex flex-col gap-6">
      {/* Telemetry: one quiet line */}
      <div className="flex items-center gap-x-3 gap-y-1 flex-wrap font-mono text-xs text-muted-foreground tabular-nums min-w-0">
        <span className="inline-flex items-center gap-1.5">
          <Dot tone="ok" />
          {t.survived} survived
        </span>
        <span aria-hidden="true">·</span>
        <span className="inline-flex items-center gap-1.5">
          <Dot tone="fail" />
          {t.dead} abandoned
        </span>
        {t.running > 0 && (
          <>
            <span aria-hidden="true">·</span>
            <span className="inline-flex items-center gap-1.5">
              <Dot tone="live" pulse />
              {t.running} running
            </span>
          </>
        )}
        <span aria-hidden="true">·</span>
        <span>
          {t.done}/{t.total} finished
        </span>
        {state.targetUrl && (
          <span className="ml-auto truncate max-sm:hidden">
            {state.targetUrl}
          </span>
        )}
      </div>

      <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
        {state.order.map((id) => {
          const live = state.personas[id];
          if (!live) return null;
          return (
            <PersonaTile
              key={id}
              live={live}
              coordSpace={coordSpace}
              backdrop={backdrop}
            />
          );
        })}
      </div>

      {reportReady && onSeeReport && (
        <div className="flex justify-center pt-4">
          <button
            type="button"
            className="px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
            onClick={onSeeReport}
          >
            View the report
          </button>
        </div>
      )}
    </section>
  );
}
