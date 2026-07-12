// The one playful element (v3 "Quiet workspace"): a vital line shrunk to a
// whisper. A 1px sparkline, full width x 12px, at the very bottom of each
// persona tile:
//
//   running   -> a small dim-gray blip drifting leftward on a hairline
//   success   -> flat dim-green line (calm, settled)
//   abandoned -> flat red line with a tiny gap at the death point
//   pending   -> barely-there neutral baseline
//
// Implementation notes:
// - The running state renders a wide fixed-scale viewBox (1440x12) with
//   preserveAspectRatio="xMinYMid slice" so the blip never stretches — narrow
//   containers crop the right side. The blip <g> drifts left by exactly one
//   120-unit cycle via a CSS transform loop (.vital-scroll in styles.css).
// - Flat states use preserveAspectRatio="none" (a horizontal line is
//   invariant under stretch) + vector-effect="non-scaling-stroke" so the
//   stroke stays 1px; the gap sits at the death step.
// - prefers-reduced-motion freezes the drift to a static frame (global rule
//   in styles.css); every state stays legible frozen.
//
// FlatlineGlyph is the same story in 120x24 for the launch page: a short
// hairline that blips once, then flatlines.

import type { TileStatus } from "../types";

const H = 12; // viewBox height
const BASE = 8; // baseline y
const CYCLE = 120; // one blip cycle, in SVG units == px at 1:1
const SPAN = 1440; // visible viewBox width (crops beyond container width)

/** One small blip starting at x, then flat to the end of the cycle. */
function blip(x: number): string {
  return [
    `H${x + 46}`,
    `L${x + 52} 3`,
    `L${x + 57} 10.5`,
    `L${x + 60} ${BASE}`,
    `H${x + CYCLE}`,
  ].join(" ");
}

function trace(): string {
  // One extra cycle beyond the viewBox so the -120px drift loops seamlessly.
  const n = SPAN / CYCLE + 1;
  let d = `M0 ${BASE} `;
  for (let i = 0; i < n; i++) d += blip(i * CYCLE) + " ";
  return d;
}

const RUN_TRACE = trace();

interface Props {
  status: TileStatus;
  /** 0..1 position of the flatline gap (death step / step budget). */
  deathFrac?: number;
  /** Rendered strip height in px. */
  height?: number;
  className?: string;
}

const LABEL: Record<TileStatus, string> = {
  pending: "vital line: standby",
  running: "vital line: pulse",
  success: "vital line: steady",
  abandoned: "vital line: flat, with a gap at the death point",
};

export function VitalLine({
  status,
  deathFrac = 0.62,
  height = 12,
  className = "",
}: Props) {
  if (status === "running") {
    return (
      <svg
        className={`block w-full ${className}`}
        height={height}
        viewBox={`0 0 ${SPAN} ${H}`}
        preserveAspectRatio="xMinYMid slice"
        role="img"
        aria-label={LABEL[status]}
      >
        <g className="vital-scroll">
          <path
            d={RUN_TRACE}
            fill="none"
            stroke="var(--idle)"
            strokeWidth={1}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.55}
          />
        </g>
      </svg>
    );
  }

  if (status === "abandoned") {
    const gap = Math.min(Math.max(deathFrac, 0.08), 0.92) * 100;
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
          x2={gap - 2}
          y2={BASE}
          stroke="var(--fail)"
          strokeWidth={1}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <line
          x1={gap + 2}
          y1={BASE}
          x2={100}
          y2={BASE}
          stroke="var(--fail)"
          strokeWidth={1}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          opacity={0.45}
        />
      </svg>
    );
  }

  const ok = status === "success";
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
        stroke={ok ? "var(--ok)" : "var(--idle)"}
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
        opacity={ok ? 0.7 : 0.25}
      />
    </svg>
  );
}

/** The launch-page mark: a short hairline that blips once, then flatlines.
 *  The whole product story in 24x120px. Drawn in currentColor. */
export function FlatlineGlyph({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`block ${className}`}
      width={120}
      height={24}
      viewBox="0 0 120 24"
      fill="none"
      role="img"
      aria-label="A vital line that blips once, then flatlines"
    >
      <path
        d="M0 15 H42 L49 5 L55 19.5 L59 15 H120"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
