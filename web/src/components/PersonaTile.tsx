import { motion } from "framer-motion";
import type { PersonaLiveState, TileStatus, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { perceptionFilter, perturbationBadges } from "../theme";

const BASE = import.meta.env.BASE_URL || "/";
const FALLBACK_BG = `${BASE}fixtures/sample_screenshot.png`;

interface Props {
  live: PersonaLiveState;
  index: number;
  coordSpace?: Viewport; // pixel space of x/y coords (default persona viewport)
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
      : status === "abandoned"
        ? "bg-red-500"
        : "border border-muted-foreground/40";
  return (
    <span
      className={`w-2 h-2 rounded-full shrink-0 ${cls}`}
      role="img"
      aria-label={status}
    />
  );
}

export function PersonaTile({ live, index, coordSpace }: Props) {
  const { persona, status, lastCaption, lastThumb, step, failure } = live;
  const badges = perturbationBadges(persona);
  const space: Viewport =
    coordSpace ?? persona.viewport ?? { width: 1280, height: 800 };

  const dead = status === "abandoned";
  const won = status === "success";
  const running = status === "running";
  const pending = status === "pending";

  const marker = failure?.coords ?? null;
  const markerLeft = marker
    ? Math.min(Math.max(marker[0] / space.width, 0), 1) * 100
    : 0;
  const markerTop = marker
    ? Math.min(Math.max(marker[1] / space.height, 0), 1) * 100
    : 0;

  const bg = lastThumb || FALLBACK_BG;
  const filter = lastThumb ? undefined : perceptionFilter(persona);

  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      className={`rounded-2xl border bg-background overflow-hidden transition-colors duration-300 ${
        won
          ? "border-emerald-500/40"
          : dead
            ? "border-red-500/40"
            : running
              ? "border-foreground/30"
              : "border-border"
      } ${pending ? "opacity-60" : ""}`}
      aria-label={`${persona.name} — ${
        won ? "completed" : dead ? "abandoned" : running ? "running" : "waiting"
      }`}
    >
      {/* Screenshot / thumbnail layer */}
      <div className="relative aspect-[16/10] bg-muted/30 overflow-hidden">
        <div
          className={`absolute inset-0 bg-cover bg-top transition-[filter] duration-500 ${
            dead ? "grayscale opacity-60" : ""
          }`}
          style={{ backgroundImage: `url("${bg}")`, filter }}
          aria-hidden="true"
        />
        <div className="scanlines" aria-hidden="true" />

        {/* functional state tints — subtle opacity layers, never saturated fills */}
        {dead && (
          <div className="absolute inset-0 bg-red-500/10" aria-hidden="true" />
        )}
        {won && (
          <div className="absolute inset-0 bg-emerald-500/5" aria-hidden="true" />
        )}

        {/* the death pixel — crosshair frozen where the persona abandoned */}
        {dead && marker && (
          <span
            className="absolute w-[26px] h-[26px] -ml-[13px] -mt-[13px] pointer-events-none"
            style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
            title={`Abandoned at ${marker[0]}, ${marker[1]}`}
          >
            <span className="absolute left-1/2 top-0 bottom-0 w-px -ml-px bg-red-500" />
            <span className="absolute top-1/2 left-0 right-0 h-px -mt-px bg-red-500" />
            <motion.span
              className="absolute inset-1 rounded-full border border-red-500"
              animate={{ scale: [0.6, 1.7], opacity: [1, 0] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
              aria-hidden="true"
            />
            <span className="absolute left-full top-0 ml-1.5 text-[10px] font-mono text-red-500 whitespace-nowrap">
              {marker[0]},{marker[1]}
            </span>
          </span>
        )}

        {/* Footer overlay: death stamp, win note, or live caption */}
        {dead && failure ? (
          <div className="absolute inset-x-0 bottom-0 px-4 pb-3 pt-8 bg-gradient-to-t from-background/90 to-transparent">
            <p className="text-sm font-medium text-red-500">
              {OUTCOME_LABELS[failure.outcome]} · step{" "}
              <span className="tabular-nums">
                {failure.stepsSurvived ?? step}
              </span>
            </p>
            {failure.reason && (
              <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                “{failure.reason}”
              </p>
            )}
          </div>
        ) : (
          <div className="absolute inset-x-0 bottom-0 px-4 pb-3 pt-8 bg-gradient-to-t from-background/90 to-transparent flex items-center gap-2 text-xs">
            <span className="font-mono text-muted-foreground tabular-nums shrink-0">
              {pending ? "standby" : `step ${step}`}
            </span>
            <span
              className={`truncate ${
                won ? "text-emerald-500 font-medium" : "text-foreground"
              }`}
            >
              {won ? "Completed the task" : lastCaption}
            </span>
            {running && (
              <motion.span
                className="w-px h-3.5 bg-foreground shrink-0"
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 1.1, repeat: Infinity }}
                aria-hidden="true"
              />
            )}
          </div>
        )}
      </div>

      {/* Identity bar: status dot + name + degraded-channel labels */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-t border-border min-h-10">
        <StatusDot status={status} />
        <span
          className="text-sm font-medium truncate"
          title={persona.blurb || persona.name}
        >
          {persona.name}
        </span>
        <span className="flex gap-2 overflow-hidden ml-auto">
          {badges.map((b) => (
            <span
              key={b.kind}
              title={b.title}
              className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider whitespace-nowrap"
            >
              {b.text}
            </span>
          ))}
        </span>
      </div>
    </motion.article>
  );
}
