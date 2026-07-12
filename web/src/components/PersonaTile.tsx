import { motion } from "framer-motion";
import type { PersonaLiveState, TileStatus, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { perceptionFilter, perturbationBadges } from "../theme";
import { VitalLine } from "./VitalLine";

const BASE = import.meta.env.BASE_URL || "/";
const FALLBACK_BG = `${BASE}fixtures/sample_screenshot.png`;

interface Props {
  live: PersonaLiveState;
  index: number;
  coordSpace?: Viewport; // pixel space of x/y coords (default persona viewport)
}

function StatusLamp({ status }: { status: TileStatus }) {
  if (status === "running") {
    return (
      <motion.span
        className="w-1.5 h-1.5 rounded-full bg-live shrink-0"
        animate={{ opacity: [1, 0.35, 1] }}
        transition={{ duration: 1.6, repeat: Infinity }}
        role="img"
        aria-label="running"
      />
    );
  }
  const cls =
    status === "success"
      ? "bg-ok"
      : status === "abandoned"
        ? "bg-fail"
        : "border border-idle/50";
  return (
    <span
      className={`w-1.5 h-1.5 rounded-full shrink-0 ${cls}`}
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
  // Flip the coord label to the left of the vertical hairline near the right edge.
  const labelFlip = markerLeft > 62;

  const bg = lastThumb || FALLBACK_BG;
  const perturbFilter = lastThumb ? undefined : perceptionFilter(persona);
  const filter = dead
    ? `grayscale(0.8) ${perturbFilter ?? ""}`.trim()
    : perturbFilter;

  const stepsSurvived = failure?.stepsSurvived ?? step;
  const deathFrac = stepsSurvived / Math.max(persona.max_steps ?? 12, 1);

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      className={`rounded-lg border border-border bg-panel overflow-hidden flex flex-col ${
        pending ? "opacity-60" : ""
      }`}
      aria-label={`${persona.name} — ${
        won ? "survived" : dead ? "died" : running ? "running" : "standby"
      }`}
    >
      {/* Identity row: lamp + name (display face) + degraded-channel labels */}
      <header className="flex items-center gap-2 px-3 pt-2.5 pb-2 min-h-9">
        <StatusLamp status={status} />
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
              className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest whitespace-nowrap"
            >
              {b.text}
            </span>
          ))}
        </span>
      </header>

      {/* Bezel-framed specimen viewport */}
      <div className="px-3">
        <div
          className={`viewport-bezel relative aspect-[16/10] rounded-md overflow-hidden bg-background ${
            dead
              ? "border-2 border-fail"
              : won
                ? "border border-ok"
                : "border border-border"
          }`}
        >
          <div
            className="absolute inset-0 bg-cover bg-top transition-[filter] duration-500"
            style={{ backgroundImage: `url("${bg}")`, filter }}
            aria-hidden="true"
          />
          <div className="scanlines" aria-hidden="true" />

          {/* The death pixel — calibration crosshair frozen where they gave up */}
          {dead && marker && (
            <div
              className="absolute inset-0 pointer-events-none"
              title={`Abandoned at ${marker[0]}, ${marker[1]}`}
              aria-hidden="true"
            >
              {/* full-height / full-width hairlines */}
              <span
                className="absolute top-0 bottom-0 w-px bg-fail/70"
                style={{ left: `${markerLeft}%` }}
              />
              <span
                className="absolute left-0 right-0 h-px bg-fail/70"
                style={{ top: `${markerTop}%` }}
              />
              {/* center ring */}
              <span
                className="absolute w-3 h-3 -ml-1.5 -mt-1.5 rounded-full border border-fail bg-fail/15"
                style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
              />
              {/* coords ride the top edge of the vertical hairline — never
                  near the epitaph, which lives below the viewport */}
              <span
                className={`absolute top-0.5 text-[9px] font-mono text-fail whitespace-nowrap bg-background/85 rounded-sm px-1 ${
                  labelFlip ? "-translate-x-full -ml-0.5" : "ml-0.5"
                }`}
                style={{ left: `${markerLeft}%` }}
              >
                {marker[0]},{marker[1]}
              </span>
            </div>
          )}

          {/* Corner outcome tag */}
          {(dead || won) && (
            <span
              className={`absolute top-0 right-0 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-widest rounded-bl-md ${
                dead ? "bg-fail" : "bg-ok"
              } text-background`}
            >
              {dead ? "died" : "survived"} · step{" "}
              {dead ? stepsSurvived : step}
            </span>
          )}
        </div>
      </div>

      {/* Console lines */}
      <div className="px-3 pt-2 pb-1 font-mono text-xs flex flex-col gap-1">
        <p className="flex items-baseline gap-1.5 min-w-0">
          <span className="text-muted-foreground shrink-0" aria-hidden="true">
            &gt;
          </span>
          <span
            className={`truncate ${
              won
                ? "text-ok"
                : pending
                  ? "text-muted-foreground"
                  : "text-foreground"
            }`}
          >
            {won
              ? "Completed the task"
              : pending
                ? "standby"
                : `step ${step} · ${lastCaption}`}
          </span>
          {running && (
            <span
              className="caret-blink w-[5px] h-3 bg-live shrink-0 self-center"
              aria-hidden="true"
            />
          )}
        </p>
        {dead && failure && (
          <p className="flex items-baseline gap-1.5 min-w-0 text-fail">
            <span className="shrink-0" aria-hidden="true">
              &gt;
            </span>
            <span className="line-clamp-2">
              {OUTCOME_LABELS[failure.outcome].toLowerCase()}
              {failure.reason ? ` — “${failure.reason}”` : ""}
            </span>
          </p>
        )}
      </div>

      {/* Vital sign — pinned to the bottom of the specimen card */}
      <div className="mt-auto">
        <VitalLine status={status} deathFrac={deathFrac} height={26} />
      </div>
    </motion.article>
  );
}
