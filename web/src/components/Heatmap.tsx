import { useState } from "react";
import type { HeatPoint, Viewport } from "../types";
import { FAIL_HEX } from "../theme";

const BASE = import.meta.env.BASE_URL || "/";
const SAMPLE = `${BASE}fixtures/sample_screenshot.png`;

// Live runs use a 1280x800 viewport; the backend saves the real target
// screenshot at that size. The bundled sample is 640x480.
const LIVE_SPACE: Viewport = { width: 1280, height: 800 };
const SAMPLE_SPACE: Viewport = { width: 640, height: 480 };

interface Props {
  points: HeatPoint[];
  // Live target screenshot URL (${API_BASE}/artifacts/${run_id}/target.png).
  // When present, it is the primary backdrop and coords are treated as 1280x800.
  // If it fails to load, we fall back to the bundled sample at 640x480.
  liveBackdrop?: string;
  // Pixel space the point coords live in when NOT using the live backdrop
  // (offline demo authors coords against the 640x480 sample).
  coordSpace?: Viewport;
}

export function Heatmap({ points, liveBackdrop, coordSpace }: Props) {
  const [liveFailed, setLiveFailed] = useState(false);
  const useLive = Boolean(liveBackdrop) && !liveFailed;

  const img = useLive ? (liveBackdrop as string) : SAMPLE;
  const space = useLive ? LIVE_SPACE : coordSpace ?? SAMPLE_SPACE;
  const maxW = Math.max(1, ...points.map((p) => p.weight ?? 1));

  return (
    <figure className="p-5 rounded-lg border border-border bg-panel m-0">
      <figcaption className="mb-5">
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-1">
          Abandonment heatmap
        </p>
        <p className="text-sm text-muted-foreground">
          where, on your actual page, users give up
        </p>
      </figcaption>

      <div
        className="viewport-bezel relative w-full rounded-md overflow-hidden border border-border bg-background"
        style={{ aspectRatio: `${space.width} / ${space.height}` }}
      >
        <img
          className="block w-full h-full object-cover grayscale-[0.3] opacity-80"
          src={img}
          alt="Target page"
          onError={() => {
            if (useLive) setLiveFailed(true);
          }}
        />
        <span className="absolute top-2 left-2 z-10 text-[9px] font-mono uppercase tracking-widest text-muted-foreground bg-background/85 border border-border rounded-sm px-1.5 py-0.5">
          {useLive ? "Live target page" : "Sample page"}
        </span>
        {points.map((p, i) => {
          const left = (p.x / space.width) * 100;
          const top = (p.y / space.height) * 100;
          const w = p.weight ?? 1;
          const size = 90 + (w / maxW) * 120;
          return (
            <div
              key={`${p.persona_id}-${i}`}
              className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full pointer-events-none mix-blend-multiply dark:mix-blend-screen"
              style={{
                left: `${left}%`,
                top: `${top}%`,
                width: size,
                height: size,
                background: `radial-gradient(circle, ${FAIL_HEX}cc 0%, ${FAIL_HEX}66 35%, ${FAIL_HEX}00 70%)`,
              }}
              title={`${p.persona_id || "abandon"} @ ${p.x},${p.y}`}
            />
          );
        })}
        {points.map((p, i) => {
          const left = (p.x / space.width) * 100;
          const top = (p.y / space.height) * 100;
          return (
            <svg
              key={`dot-${p.persona_id}-${i}`}
              className="absolute w-3.5 h-3.5 -translate-x-1/2 -translate-y-1/2 text-fail cursor-help"
              style={{ left: `${left}%`, top: `${top}%` }}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <title>{`${p.persona_id || "abandon"} @ ${p.x},${p.y}`}</title>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={3}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          );
        })}
      </div>
      <p className="mt-4 font-mono text-[11px] text-muted-foreground tabular-nums">
        {points.length} abandonment{" "}
        {points.length === 1 ? "point" : "points"} · each mark is a persona
        that gave up here
      </p>
    </figure>
  );
}
