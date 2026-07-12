// The signature element: a per-persona vital-sign trace (EKG strip).
//
//   running   -> repeating heartbeat pulse scrolling leftward in amber
//   success   -> settles into a calm, slower pulse in emerald
//   abandoned -> FLATLINE: flat red line with a break at the death step;
//                the animation stops dead (nothing moves on a dead specimen)
//   pending   -> faint neutral baseline (standby)
//
// Implementation notes:
// - The live states render a wide fixed-scale viewBox (1440x24) with
//   preserveAspectRatio="xMinYMid slice" so the waveform NEVER stretches —
//   narrow containers simply crop the right side. The pulse <g> scrolls left
//   by exactly one 120-unit cycle via a CSS transform loop (see .vital-scroll
//   in styles.css), which at 1:1 scale is 120px, so the loop is seamless.
// - The flatline uses preserveAspectRatio="none" (a horizontal line is
//   invariant under horizontal stretch) with vector-effect="non-scaling-stroke"
//   so stroke weight stays constant; the break sits at the death step.
// - prefers-reduced-motion collapses the scroll animation to a static frame
//   (global rule in styles.css); every state remains legible when frozen.

import type { TileStatus } from "../types";

const H = 24; // viewBox height
const BASE = 17; // baseline y
const CYCLE = 120; // one heartbeat cycle, in SVG units == px at 1:1
const SPAN = 1440; // visible viewBox width (crops beyond container width)

/** One full-strength heartbeat cycle starting at x (P wave, QRS, T wave). */
function beat(x: number): string {
  return [
    `H${x + 30}`,
    `L${x + 36} 13.5`,
    `L${x + 42} ${BASE}`, // P wave
    `H${x + 52}`,
    `L${x + 55} 19.5`, // Q
    `L${x + 60} 3.5`, // R spike
    `L${x + 65} 22`, // S
    `L${x + 68} ${BASE}`,
    `H${x + 78}`,
    `L${x + 84} 13`,
    `L${x + 90} ${BASE}`, // T wave
    `H${x + CYCLE}`,
  ].join(" ");
}

/** A calm survivor's cycle: same rhythm, gentler amplitude. */
function calmBeat(x: number): string {
  return [
    `H${x + 34}`,
    `L${x + 40} 15`,
    `L${x + 46} ${BASE}`,
    `H${x + 56}`,
    `L${x + 60} 18.5`,
    `L${x + 64} 9`,
    `L${x + 68} 19.5`,
    `L${x + 71} ${BASE}`,
    `H${x + 82}`,
    `L${x + 88} 14.5`,
    `L${x + 94} ${BASE}`,
    `H${x + CYCLE}`,
  ].join(" ");
}

function trace(cycle: (x: number) => string): string {
  // One extra cycle beyond the viewBox so the -120px scroll loops seamlessly.
  const n = SPAN / CYCLE + 1;
  let d = `M0 ${BASE} `;
  for (let i = 0; i < n; i++) d += cycle(i * CYCLE) + " ";
  return d;
}

const RUN_TRACE = trace(beat);
const CALM_TRACE = trace(calmBeat);

interface Props {
  status: TileStatus;
  /** 0..1 position of the flatline break (death step / step budget). */
  deathFrac?: number;
  /** Rendered strip height in px (24-28 reads best). */
  height?: number;
  className?: string;
}

const LABEL: Record<TileStatus, string> = {
  pending: "vital sign: standby",
  running: "vital sign: pulse",
  success: "vital sign: steady pulse",
  abandoned: "vital sign: flatline",
};

export function VitalLine({
  status,
  deathFrac = 0.62,
  height = 26,
  className = "",
}: Props) {
  if (status === "abandoned") {
    const gap = Math.min(Math.max(deathFrac, 0.12), 0.88) * 100;
    return (
      <svg
        className={`block w-full ${className}`}
        height={height}
        viewBox={`0 0 100 ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={LABEL[status]}
      >
        {/* trace up to the death step, ending in one collapsing blip */}
        <path
          d={`M0 ${BASE} H${gap - 8} L${gap - 6} 11 L${gap - 4} 20.5 L${gap - 2.6} ${BASE}`}
          fill="none"
          stroke="var(--fail)"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        {/* the break — then a dead-flat line to the edge */}
        <line
          x1={gap + 2.6}
          y1={BASE}
          x2={100}
          y2={BASE}
          stroke="var(--fail)"
          strokeWidth={1.5}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          opacity={0.55}
        />
      </svg>
    );
  }

  if (status === "pending") {
    return (
      <svg
        className={`block w-full ${className}`}
        height={height}
        viewBox={`0 0 100 ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={LABEL[status]}
      >
        <line
          x1={0}
          y1={BASE}
          x2={100}
          y2={BASE}
          stroke="var(--idle)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
          opacity={0.35}
        />
      </svg>
    );
  }

  const ok = status === "success";
  return (
    <svg
      className={`block w-full ${className}`}
      height={height}
      viewBox={`0 0 ${SPAN} ${H}`}
      preserveAspectRatio="xMinYMid slice"
      role="img"
      aria-label={LABEL[status]}
    >
      {/* faint baseline track behind the pulse */}
      <line
        x1={0}
        y1={BASE}
        x2={SPAN}
        y2={BASE}
        stroke="currentColor"
        strokeWidth={1}
        opacity={0.1}
      />
      <g className={ok ? "vital-scroll-calm" : "vital-scroll"}>
        <path
          d={ok ? CALM_TRACE : RUN_TRACE}
          fill="none"
          stroke={ok ? "var(--ok)" : "var(--live)"}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}
