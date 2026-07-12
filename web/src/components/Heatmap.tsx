import { useState } from "react";
import type { HeatPoint } from "../types";

/**
 * Abandonment heatmap: radial-gradient blobs (weighted by `weight`) overlaid
 * on a screenshot of the target page. The SVG viewBox matches the image's
 * natural pixel size, so HeatPoint coords land on the real pixels and the
 * whole thing scales responsively together. Red-500 is the functional
 * failure accent — kept subtle via gradient opacity, never a saturated fill.
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
    <div className="relative inline-block max-w-full rounded-2xl border border-border bg-background overflow-hidden">
      <img
        className="block max-w-full h-auto grayscale-[0.5] opacity-90"
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
          className="absolute inset-0 w-full h-full"
          viewBox={`0 0 ${dims.w} ${dims.h}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${points.length} abandonment points on the target page`}
        >
          <defs>
            <radialGradient id="sl-heat">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.55" />
              <stop offset="45%" stopColor="#ef4444" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
            </radialGradient>
          </defs>
          {points.map((p, i) => (
            <g key={i}>
              <circle
                cx={p.x}
                cy={p.y}
                r={34 * Math.sqrt(p.weight ?? 1)}
                fill="url(#sl-heat)"
              />
              <circle cx={p.x} cy={p.y} r={2.5} fill="#ef4444">
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
