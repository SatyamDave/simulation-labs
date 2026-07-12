import { useState } from "react";
import type { HeatPoint, Viewport } from "../types";
import { BLOOD } from "../theme";

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
    <figure className="chart">
      <figcaption className="chart__title">
        Abandonment heatmap
        <span className="chart__sub">
          where, on your actual page, users give up
        </span>
      </figcaption>

      <div
        className="heatmap"
        style={{ aspectRatio: `${space.width} / ${space.height}` }}
      >
        <img
          className="heatmap__img"
          src={img}
          alt="Target page"
          onError={() => {
            if (useLive) setLiveFailed(true);
          }}
        />
        <div className="heatmap__scrim" />
        <span className="heatmap__source">
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
              className="heatmap__blob"
              style={{
                left: `${left}%`,
                top: `${top}%`,
                width: size,
                height: size,
                background: `radial-gradient(circle, ${BLOOD}cc 0%, ${BLOOD}66 35%, ${BLOOD}00 70%)`,
              }}
              title={`${p.persona_id || "abandon"} @ ${p.x},${p.y}`}
            />
          );
        })}
        {points.map((p, i) => {
          const left = (p.x / space.width) * 100;
          const top = (p.y / space.height) * 100;
          return (
            <div
              key={`dot-${p.persona_id}-${i}`}
              className="heatmap__x"
              style={{ left: `${left}%`, top: `${top}%` }}
              title={`${p.persona_id || "abandon"} @ ${p.x},${p.y}`}
            >
              ✕
            </div>
          );
        })}
      </div>
      <div className="heatmap__caption">
        {points.length} abandonment {points.length === 1 ? "point" : "points"} ·
        each ✕ marks a persona that gave up here
      </div>
    </figure>
  );
}
