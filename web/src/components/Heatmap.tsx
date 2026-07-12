import type { HeatPoint, Viewport } from "../types";
import { BLOOD } from "../theme";

const BASE = import.meta.env.BASE_URL || "/";
const SAMPLE = `${BASE}fixtures/sample_screenshot.png`;

interface Props {
  points: HeatPoint[];
  // Backdrop screenshot; defaults to the bundled sample. The RunReport does not
  // carry a target screenshot, so the sample stands in unless one is provided.
  backdrop?: string;
  // Pixel space the point coords live in. Offline coords fit the 640x480 sample.
  coordSpace?: Viewport;
}

export function Heatmap({ points, backdrop, coordSpace }: Props) {
  const space = coordSpace ?? { width: 640, height: 480 };
  const img = backdrop || SAMPLE;
  const maxW = Math.max(1, ...points.map((p) => p.weight ?? 1));

  return (
    <figure className="chart">
      <figcaption className="chart__title">
        Abandonment heatmap
        <span className="chart__sub">
          where, on your actual page, users die
        </span>
      </figcaption>

      <div className="heatmap" style={{ aspectRatio: `${space.width} / ${space.height}` }}>
        <img className="heatmap__img" src={img} alt="Target page" />
        <div className="heatmap__scrim" />
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
        each ✕ is a persona that gave up here
      </div>
    </figure>
  );
}
