// Completion-trend-over-deploys line. Dependency-free inline SVG so it stays
// tiny and theme-safe (strokes/fills use the app's functional CSS vars). One
// point per finished run, oldest -> newest; a point that dropped vs the prior
// run is a regression and draws in --fail. The emphasized last point is the
// current state. Optional `baseline` draws a faint gridline at the flow's
// baseline completion so a dip below it is obvious.

interface TrendChartProps {
  points: { created_at: string; completion_rate: number }[];
  // Latest baseline completion (0..1) for this flow, if one is set.
  baseline?: number;
}

// viewBox geometry — the SVG scales to 100% width via preserveAspectRatio.
const W = 640;
const H = 200;
const PAD = { top: 18, right: 14, bottom: 26, left: 14 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export function TrendChart({ points, baseline }: TrendChartProps) {
  // Empty state: nothing to plot yet.
  if (points.length === 0) {
    return (
      <div className="flex h-[160px] items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground">
        No completion data to trend yet.
      </div>
    );
  }

  const n = points.length;
  // Completion is a rate 0..1; clamp defensively so a stray value can't blow
  // out the plot. The y-domain is the full 0..100% so deploys are comparable.
  const clamp = (v: number) => Math.max(0, Math.min(1, v));

  const x = (i: number) =>
    n === 1 ? PAD.left + PLOT_W / 2 : PAD.left + (i / (n - 1)) * PLOT_W;
  const y = (v: number) => PAD.top + (1 - clamp(v)) * PLOT_H;

  const coords = points.map((p, i) => ({
    px: x(i),
    py: y(p.completion_rate),
    value: p.completion_rate,
    at: p.created_at,
    // Regression: strictly lower completion than the previous deploy.
    regression: i > 0 && p.completion_rate < points[i - 1].completion_rate,
  }));

  const linePath = coords
    .map((c, i) => `${i === 0 ? "M" : "L"} ${c.px.toFixed(1)} ${c.py.toFixed(1)}`)
    .join(" ");

  // Area fill drops from the line down to the plot floor and closes.
  const floor = PAD.top + PLOT_H;
  const areaPath =
    n === 1
      ? "" // a single point has no meaningful area
      : `${linePath} L ${coords[n - 1].px.toFixed(1)} ${floor} L ${coords[0].px.toFixed(1)} ${floor} Z`;

  const last = coords[n - 1];
  const first = points[0];
  const lastPoint = points[n - 1];
  const baseY = baseline != null ? y(baseline) : null;

  const desc =
    n === 1
      ? `One run at ${pct(lastPoint.completion_rate)} completion.`
      : `Completion moved from ${pct(first.completion_rate)} to ${pct(
          lastPoint.completion_rate
        )} across ${n} runs${
          baseline != null ? `; baseline ${pct(baseline)}` : ""
        }.`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Completion trend over deploys"
      className="block h-auto w-full"
    >
      <title>Completion trend over deploys</title>
      <desc>{desc}</desc>

      {/* horizontal gridlines at 0 / 50 / 100% */}
      {[0, 0.5, 1].map((g) => (
        <line
          key={g}
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(g)}
          y2={y(g)}
          stroke="var(--border)"
          strokeWidth={1}
        />
      ))}
      {[0, 0.5, 1].map((g) => (
        <text
          key={`lbl-${g}`}
          x={PAD.left}
          y={y(g) - 3}
          fill="var(--muted-foreground)"
          fontSize={10}
          className="tabular-nums"
        >
          {pct(g)}
        </text>
      ))}

      {/* baseline reference line */}
      {baseY != null && (
        <>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={baseY}
            y2={baseY}
            stroke="var(--idle)"
            strokeWidth={1}
            strokeDasharray="4 4"
            opacity={0.7}
          />
          <text
            x={W - PAD.right}
            y={baseY - 3}
            textAnchor="end"
            fill="var(--muted-foreground)"
            fontSize={10}
            className="tabular-nums"
          >
            baseline {pct(baseline!)}
          </text>
        </>
      )}

      {/* area fill under the line */}
      {areaPath && (
        <path d={areaPath} fill="var(--foreground)" opacity={0.06} />
      )}

      {/* the trend line */}
      {n > 1 && (
        <path
          d={linePath}
          fill="none"
          stroke="var(--foreground)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity={0.85}
        />
      )}

      {/* per-deploy dots; regressions in --fail, others quiet */}
      {coords.map((c, i) => {
        const isLast = i === n - 1;
        const fill = c.regression ? "var(--fail)" : "var(--foreground)";
        return (
          <circle
            key={c.at + i}
            cx={c.px}
            cy={c.py}
            r={isLast ? 5 : c.regression ? 4 : 3}
            fill={fill}
            stroke="var(--card)"
            strokeWidth={isLast ? 2 : 1}
          >
            <title>{`${pct(c.value)} completion${
              c.regression ? " (regression)" : ""
            }`}</title>
          </circle>
        );
      })}

      {/* emphasize the current value next to the last point */}
      <text
        x={Math.min(last.px + 8, W - PAD.right)}
        y={Math.max(last.py - 8, PAD.top + 8)}
        textAnchor={last.px > W - PAD.right - 40 ? "end" : "start"}
        fill="var(--foreground)"
        fontSize={12}
        fontWeight={600}
        className="tabular-nums"
      >
        {pct(last.value)}
      </text>
    </svg>
  );
}
