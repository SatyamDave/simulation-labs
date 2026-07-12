import { motion } from "framer-motion";
import type { PersonaConfig, PerturbationKind } from "../types";
import type { PersonaLive, TileStatus } from "../useRunStream";

/** Tiny uppercase mono labels for each degraded channel (no icons, no emoji). */
const PERTURBATION_LABEL: Record<PerturbationKind, { text: string; title: string }> = {
  blur: { text: "blur", title: "blur (low vision)" },
  downscale: { text: "downscale", title: "downscale (low acuity)" },
  cvd: { text: "cvd", title: "color-vision deficiency" },
  tremor: { text: "tremor", title: "hand tremor" },
  small_viewport: { text: "viewport", title: "small viewport" },
  impatience: { text: "impatient", title: "impatience (tight budget)" },
  low_literacy: { text: "literal", title: "literal reading" },
};

const OUTCOME_STAMP: Record<string, string> = {
  step_budget: "Ran out of steps",
  time_budget: "Ran out of time",
  stuck: "Gave up",
  error: "Session crashed",
};

/** Map viewport-pixel coords to a percentage position inside the tile screen. */
function toPercent(
  coords: [number, number],
  viewport: { width: number; height: number },
): { left: string; top: string } {
  const x = Math.min(Math.max(coords[0] / viewport.width, 0), 1);
  const y = Math.min(Math.max(coords[1] / viewport.height, 0), 1);
  return { left: `${(x * 100).toFixed(2)}%`, top: `${(y * 100).toFixed(2)}%` };
}

function perturbationText(kind: PerturbationKind, persona: PersonaConfig): string {
  if (kind === "small_viewport" && persona.viewport) {
    return `${persona.viewport.width}×${persona.viewport.height}`;
  }
  return PERTURBATION_LABEL[kind]?.text ?? kind;
}

function StatusDot({ status }: { status: TileStatus }) {
  if (status === "running") {
    return (
      <motion.span
        className="w-2 h-2 rounded-full bg-emerald-500 shrink-0"
        animate={{ scale: [1, 1.2, 1] }}
        transition={{ duration: 2, repeat: Infinity }}
        role="img"
        aria-label="running"
      />
    );
  }
  const cls =
    status === "success"
      ? "bg-emerald-500"
      : status === "dead"
        ? "bg-red-500"
        : status === "error"
          ? "bg-muted-foreground"
          : "border border-muted-foreground/40";
  return (
    <span
      className={`w-2 h-2 rounded-full shrink-0 ${cls}`}
      role="img"
      aria-label={status}
    />
  );
}

export default function PersonaTile({
  live,
  index = 0,
}: {
  live: PersonaLive;
  index?: number;
}) {
  const { persona, status, lastCaption, lastThumb, step, lastXY, failure } = live;
  const viewport = persona.viewport ?? { width: 1280, height: 800 };
  const dead = status === "dead" || status === "error";
  const perturbations = persona.active_perturbations ?? [];

  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      className={`rounded-2xl border bg-background overflow-hidden transition-colors duration-300 ${
        status === "success"
          ? "border-emerald-500/40"
          : dead
            ? "border-red-500/40"
            : "border-border"
      }`}
      aria-label={`${persona.name} — ${status}`}
    >
      <div className="relative aspect-[16/10] bg-muted/30 overflow-hidden">
        {lastThumb ? (
          <img
            className="absolute inset-0 w-full h-full object-cover"
            src={lastThumb}
            alt={`Latest frame for ${persona.name}`}
          />
        ) : (
          !dead && (
            <div
              className="absolute inset-0 flex flex-col items-center justify-center gap-2"
              aria-hidden="true"
            >
              <svg
                className="w-5 h-5 text-muted-foreground/40"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v9a2 2 0 002 2z"
                />
              </svg>
              <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
                {status === "pending"
                  ? "standby"
                  : status === "success"
                    ? "survived"
                    : "live session"}
              </span>
            </div>
          )
        )}
        <div className="scanlines" aria-hidden="true" />

        {/* functional state tints — subtle opacity layers, never saturated fills */}
        {dead && <div className="absolute inset-0 bg-red-500/10" aria-hidden="true" />}
        {status === "success" && (
          <div className="absolute inset-0 bg-emerald-500/5" aria-hidden="true" />
        )}

        {/* transient ping at the last action's coords while running */}
        {status === "running" && lastXY && (
          <motion.span
            key={`${step}-${lastXY[0]}-${lastXY[1]}`}
            className="absolute w-3.5 h-3.5 -ml-[7px] -mt-[7px] rounded-full border-2 border-emerald-500 pointer-events-none"
            style={toPercent(lastXY, viewport)}
            initial={{ scale: 0.4, opacity: 0.9 }}
            animate={{ scale: 2, opacity: 0 }}
            transition={{ duration: 0.9, ease: "easeOut" }}
            aria-hidden="true"
          />
        )}

        {/* the death pixel — crosshair frozen where the persona abandoned */}
        {dead && failure?.coords && (
          <span
            className="absolute w-[26px] h-[26px] -ml-[13px] -mt-[13px] pointer-events-none"
            style={toPercent(failure.coords, viewport)}
            title={`abandoned at (${failure.coords[0]}, ${failure.coords[1]})`}
          >
            <span className="absolute left-1/2 top-0 bottom-0 w-px -ml-px bg-red-500" />
            <span className="absolute top-1/2 left-0 right-0 h-px -mt-px bg-red-500" />
            <motion.span
              className="absolute inset-1 rounded-full border border-red-500"
              animate={{ scale: [0.6, 1.7], opacity: [1, 0] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
              aria-hidden="true"
            />
          </span>
        )}

        {dead && failure ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center p-4 bg-background/60">
            <span className="text-sm font-medium text-red-500">
              {OUTCOME_STAMP[failure.outcome] ?? "Abandoned"} at step{" "}
              <span className="tabular-nums">{failure.stepsSurvived}</span>
            </span>
            {failure.reason && (
              <span className="text-xs text-muted-foreground max-w-[30ch] line-clamp-3">
                {failure.reason}
              </span>
            )}
          </div>
        ) : (
          <div className="absolute inset-x-0 bottom-0 px-3 pb-2 pt-6 text-xs text-foreground bg-gradient-to-t from-background/90 to-transparent whitespace-nowrap overflow-hidden text-ellipsis">
            {status === "success" ? "task complete" : lastCaption}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 px-3 py-2.5 border-t border-border min-h-10">
        <StatusDot status={status} />
        <span
          className="text-sm font-medium truncate"
          title={persona.blurb || persona.name}
        >
          {persona.name}
        </span>
        <span className="flex gap-2 overflow-hidden">
          {perturbations.map((p) => (
            <span
              key={p}
              className="text-xs font-mono text-muted-foreground uppercase tracking-wider whitespace-nowrap"
              title={PERTURBATION_LABEL[p]?.title ?? p}
            >
              {perturbationText(p, persona)}
            </span>
          ))}
        </span>
        <span className="flex-1" />
        <span className="text-xs font-mono text-muted-foreground tabular-nums whitespace-nowrap">
          {status === "pending" ? "—" : `step ${step}`}
        </span>
      </div>
    </motion.article>
  );
}
