import { motion } from "framer-motion";
import type { PersonaLiveState, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { perceptionFilter, perturbationBadges } from "../theme";
import { VitalLine } from "./VitalLine";

const BASE = import.meta.env.BASE_URL || "/";
const FALLBACK_BG = `${BASE}fixtures/sample_screenshot.png`;

interface Props {
  live: PersonaLiveState;
  coordSpace?: Viewport; // pixel space of x/y coords (default persona viewport)
}

export function PersonaTile({ live, coordSpace }: Props) {
  const { persona, status, lastCaption, lastThumb, step, failure, blockedSteps } =
    live;
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
  // Flip the coord chip to the left of the ring near the right edge.
  const chipFlip = markerLeft > 62;

  const bg = lastThumb || FALLBACK_BG;
  // Screenshots stay full color in every state; the perception filter only
  // fakes the persona's degraded view on fixture thumbnails.
  const filter = lastThumb ? undefined : perceptionFilter(persona);

  const stepsSurvived = failure?.stepsSurvived ?? step;
  const deathFrac = stepsSurvived / Math.max(persona.max_steps ?? 12, 1);

  const outcomeLine = won ? (
    <p className="flex items-center gap-1.5 font-mono text-[11px] text-ok tabular-nums">
      <span className="w-1.5 h-1.5 rounded-full bg-ok shrink-0" aria-hidden="true" />
      survived · step {step}
    </p>
  ) : dead ? (
    <p className="flex items-center gap-1.5 font-mono text-[11px] text-fail tabular-nums">
      <span className="w-1.5 h-1.5 rounded-full bg-fail shrink-0" aria-hidden="true" />
      died at step {stepsSurvived}
    </p>
  ) : running ? (
    <p className="flex items-center gap-1.5 font-mono text-[11px] text-live tabular-nums">
      <motion.span
        className="w-1.5 h-1.5 rounded-full bg-live shrink-0"
        animate={{ opacity: [1, 0.35, 1] }}
        transition={{ duration: 1.6, repeat: Infinity }}
        aria-hidden="true"
      />
      running · step {step}
    </p>
  ) : (
    <p className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
      <span
        className="w-1.5 h-1.5 rounded-full bg-idle/40 shrink-0"
        aria-hidden="true"
      />
      waiting
    </p>
  );

  return (
    <motion.article
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className={`rounded-xl border border-border bg-card flex flex-col overflow-hidden ${
        pending ? "opacity-60" : ""
      }`}
      aria-label={`${persona.name} — ${
        won ? "survived" : dead ? "died" : running ? "running" : "waiting"
      }`}
    >
      {/* Identity row: name + tiny mono perturbation tags */}
      <header className="flex items-baseline gap-2 px-4 pt-3 pb-2 min-w-0">
        <span
          className="text-sm font-medium truncate"
          title={persona.blurb || persona.name}
        >
          {persona.name}
        </span>
        <span className="flex items-center gap-2 overflow-hidden ml-auto">
          {blockedSteps > 0 && (
            <span
              className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground whitespace-nowrap"
              title={`${blockedSteps} action${
                blockedSteps === 1 ? "" : "s"
              } blocked by the NemoClaw policy gateway`}
            >
              <svg
                className="w-3 h-3 shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z"
                />
              </svg>
              {blockedSteps} blocked
            </span>
          )}
          {badges.map((b) => (
            <span
              key={b.kind}
              title={b.title}
              className="font-mono text-[10px] text-muted-foreground whitespace-nowrap"
            >
              {b.text}
            </span>
          ))}
        </span>
      </header>

      {/* Screenshot — full color, hairline frame */}
      <div className="px-4">
        <div className="relative aspect-[16/10] rounded-lg overflow-hidden border border-border bg-surface">
          <div
            className="absolute inset-0 bg-cover bg-top"
            style={{ backgroundImage: `url("${bg}")`, filter }}
            aria-hidden="true"
          />

          {/* The death pixel: a small red crosshair ring + coord chip */}
          {dead && marker && (
            <div
              className="absolute inset-0 pointer-events-none"
              title={`Abandoned at ${marker[0]}, ${marker[1]}`}
              aria-hidden="true"
            >
              <span
                className="absolute w-3.5 h-3.5 -ml-[7px] -mt-[7px] rounded-full border border-fail"
                style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
              />
              <span
                className="absolute w-[3px] h-[3px] -ml-[1.5px] -mt-[1.5px] rounded-full bg-fail"
                style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
              />
              <span
                className={`absolute -translate-y-1/2 font-mono text-[10px] text-fail whitespace-nowrap bg-background/90 border border-border rounded px-1 tabular-nums ${
                  chipFlip ? "-translate-x-full -ml-3" : "ml-3"
                }`}
                style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
              >
                {marker[0]},{marker[1]}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Caption + outcome */}
      <div className="px-4 pt-2.5 pb-3 flex flex-col gap-1.5 min-w-0">
        <p className="text-xs text-muted-foreground truncate">
          {won
            ? "Completed the task"
            : pending
              ? "Waiting to start"
              : lastCaption || "…"}
        </p>
        {outcomeLine}
        {dead && failure && (
          <p className="text-xs text-fail/80 line-clamp-2">
            {OUTCOME_LABELS[failure.outcome].toLowerCase()}
            {failure.reason ? ` — “${failure.reason}”` : ""}
          </p>
        )}
      </div>

      {/* The whisper: a 1px vital line at the very bottom */}
      <div className="mt-auto">
        <VitalLine status={status} deathFrac={deathFrac} />
      </div>
    </motion.article>
  );
}
