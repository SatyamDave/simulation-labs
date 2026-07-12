import { useState } from "react";
import type { HeatPoint } from "../types";

/**
 * Abandonment heatmap: radial-gradient blobs (weighted by `weight`) overlaid
 * on a screenshot of the target page. The SVG viewBox matches the image's
 * natural pixel size, so HeatPoint coords land on the real pixels and the
 * whole thing scales responsively together.
 */
export default function Heatmap({
  points,
  screenshotUrl,
}: {
  points: HeatPoint[];
  screenshotUrl: string;
}) {
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);

  return (
    <div className="heatmap">
      <img
        src={screenshotUrl}
        alt="Screenshot of the target page with abandonment points overlaid"
        onLoad={(e) =>
          setDims({
            w: e.currentTarget.naturalWidth,
            h: e.currentTarget.naturalHeight,
          })
        }
      />
      {dims && (
        <svg
          viewBox={`0 0 ${dims.w} ${dims.h}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${points.length} abandonment points on the target page`}
        >
          <defs>
            <radialGradient id="gp-heat">
              <stop offset="0%" stopColor="#ff6b4a" stopOpacity="0.85" />
              <stop offset="45%" stopColor="#e05252" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#e05252" stopOpacity="0" />
            </radialGradient>
          </defs>
          {points.map((p, i) => (
            <g key={i}>
              <circle
                className="heatmap__blob"
                cx={p.x}
                cy={p.y}
                r={34 * Math.sqrt(p.weight ?? 1)}
                fill="url(#gp-heat)"
              />
              <circle cx={p.x} cy={p.y} r={2.5} fill="#ffd9cf">
                <title>
                  {(p.persona_id || "persona") +
                    ` abandoned at (${p.x}, ${p.y})` +
                    ((p.weight ?? 1) !== 1 ? ` · weight ${p.weight}` : "")}
                </title>
              </circle>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}
