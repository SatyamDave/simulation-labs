// Stats dashboard for the report view: KPI stat row, the TRUE stepped
// survival curve (step-after line, inline SVG), actions-by-type breakdown and
// the per-persona statistics table. All data comes from RunInsights — server
// stats when present, the client-side fallback otherwise (see insights.ts).

import { useRef, useState } from "react";
import type {
  PersonaStats,
  RunInsights,
  SurvivalSeriesPoint,
} from "../insights";
import type { PersonaConfig } from "../types";
import { OUTCOME_LABELS } from "../types";
import {
  OUTCOME_COLOR,
  perturbationBadges,
  scoreColor,
  SERIES_CURRENT,
} from "../theme";

// ---------------------------------------------------------------------------
// Formatting helpers (shared with CompareView / IndexView)
// ---------------------------------------------------------------------------
export function fmtMs(ms: number): string {
  if (!ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

export function fmtDuration(s: number): string {
  if (!s) return "—";
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

export function timeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const sec = Math.max(0, (Date.now() - t) / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return new Date(t).toLocaleDateString();
}

// One quiet metric: big tabular number over a dim label (shared with
// CompareView's delta row). No card chrome — whitespace is the separator.
export function StatTile({
  label,
  value,
  color,
  title,
}: {
  label: string;
  value: string;
  color?: string;
  title?: string;
}) {
  return (
    <div title={title}>
      <p
        className="text-2xl font-semibold tracking-tight tabular-nums"
        style={color ? { color } : undefined}
      >
        {value}
      </p>
      <p className="font-mono text-[11px] text-muted-foreground mt-0.5">
        {label}
      </p>
    </div>
  );
}

// Small titled figure wrapper for the charts below.
function ChartFigure({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <figure>
      <figcaption className="mb-3">
        <span className="block text-sm font-medium">{title}</span>
        {sub && (
          <span className="block text-xs text-muted-foreground mt-0.5">
            {sub}
          </span>
        )}
      </figcaption>
      {children}
    </figure>
  );
}

// ---------------------------------------------------------------------------
// Stepped survival chart — step-after line(s), 1 or 2 series.
// ---------------------------------------------------------------------------
export interface StepSeries {
  label: string;
  color: string;
  points: SurvivalSeriesPoint[];
}

const W = 560;
const H = 240;
const PAD = { left: 34, right: 48, top: 12, bottom: 28 };

function aliveAt(points: SurvivalSeriesPoint[], step: number): number {
  let alive = points.length ? points[0].alive : 0;
  for (const p of points) {
    if (p.step > step) break;
    alive = p.alive;
  }
  return alive;
}

interface HoverState {
  step: number;
  xPct: number;
  entries: { label: string; color: string; alive: number }[];
}

export function SurvivalStepChart({
  series,
  title,
  sub,
}: {
  series: StepSeries[];
  title: string;
  sub?: string;
}) {
  const [hover, setHover] = useState<HoverState | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const drawn = series.filter((s) => s.points.length > 0);
  if (drawn.length === 0) return null;

  const maxStep = Math.max(1, ...drawn.flatMap((s) => s.points.map((p) => p.step)));
  const maxAlive = Math.max(1, ...drawn.flatMap((s) => s.points.map((p) => p.alive)));

  const iw = W - PAD.left - PAD.right;
  const ih = H - PAD.top - PAD.bottom;
  const x = (step: number) => PAD.left + (step / maxStep) * iw;
  const y = (alive: number) => PAD.top + (1 - alive / maxAlive) * ih;

  // Integer axis ticks, kept sparse.
  const yStep = Math.max(1, Math.ceil(maxAlive / 4));
  const yTicks: number[] = [];
  for (let v = 0; v <= maxAlive; v += yStep) yTicks.push(v);
  const xStep = Math.max(1, Math.ceil(maxStep / 6));
  const xTicks: number[] = [];
  for (let v = 0; v <= maxStep; v += xStep) xTicks.push(v);

  function stepPath(points: SurvivalSeriesPoint[]): string {
    let d = `M ${x(points[0].step)} ${y(points[0].alive)}`;
    for (let i = 1; i < points.length; i++) {
      // Step-after: the value holds until the next step, then drops.
      d += ` H ${x(points[i].step)} V ${y(points[i].alive)}`;
    }
    return d;
  }

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * W;
    const step = Math.max(
      0,
      Math.min(maxStep, Math.round(((vx - PAD.left) / iw) * maxStep))
    );
    setHover({
      step,
      xPct: (x(step) / W) * 100,
      entries: drawn.map((s) => ({
        label: s.label,
        color: s.color,
        alive: aliveAt(s.points, step),
      })),
    });
  }

  // End labels: nudge apart when two endpoints collide.
  const ends = drawn.map((s) => {
    const last = s.points[s.points.length - 1];
    return { ...s, ex: x(last.step), ey: y(last.alive), alive: last.alive };
  });
  if (ends.length === 2 && Math.abs(ends[0].ey - ends[1].ey) < 14) {
    const [a, b] = ends[0].ey <= ends[1].ey ? [ends[0], ends[1]] : [ends[1], ends[0]];
    a.ey -= 7;
    b.ey += 7;
  }

  const label = `${title}: ${drawn
    .map((s) => `${s.label} from ${s.points[0].alive} to ${s.points[s.points.length - 1].alive} over ${maxStep} steps`)
    .join("; ")}`;

  return (
    <ChartFigure title={title} sub={sub}>
      <div className="stepchart">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={label}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {/* gridlines (recessive hairlines) + y ticks */}
          {yTicks.map((v) => (
            <g key={`y${v}`}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(v)}
                y2={y(v)}
                className="stepchart__grid"
              />
              <text x={PAD.left - 7} y={y(v) + 3.5} className="stepchart__tick" textAnchor="end">
                {v}
              </text>
            </g>
          ))}
          {/* x ticks */}
          {xTicks.map((v) => (
            <text
              key={`x${v}`}
              x={x(v)}
              y={H - PAD.bottom + 16}
              className="stepchart__tick"
              textAnchor="middle"
            >
              {v}
            </text>
          ))}
          {/* baseline */}
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(0)}
            y2={y(0)}
            className="stepchart__axis"
          />

          {/* area wash (single series only — two washes would mud) */}
          {drawn.length === 1 && (
            <path
              d={`${stepPath(drawn[0].points)} V ${y(0)} H ${x(drawn[0].points[0].step)} Z`}
              fill={drawn[0].color}
              opacity={0.06}
              stroke="none"
            />
          )}

          {/* hover crosshair */}
          {hover && (
            <line
              x1={x(hover.step)}
              x2={x(hover.step)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              className="stepchart__crosshair"
            />
          )}

          {/* the stepped lines */}
          {drawn.map((s) => (
            <path
              key={s.label}
              d={stepPath(s.points)}
              fill="none"
              stroke={s.color}
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}

          {/* end markers (card ring) + direct end labels */}
          {ends.map((s) => (
            <g key={`e${s.label}`}>
              <circle cx={s.ex} cy={s.ey} r={3.5} fill={s.color} className="stepchart__dot" />
              <text x={s.ex + 8} y={s.ey + 3.5} className="stepchart__endlabel">
                {s.alive}
                {drawn.length > 1 ? ` ${s.label}` : " left"}
              </text>
            </g>
          ))}

          {/* hover markers */}
          {hover &&
            drawn.map((s) => (
              <circle
                key={`h${s.label}`}
                cx={x(hover.step)}
                cy={y(aliveAt(s.points, hover.step))}
                r={3.5}
                fill={s.color}
                className="stepchart__dot"
              />
            ))}
        </svg>
        {hover && (
          <div
            className="stepchart__tip"
            style={{
              left: `${hover.xPct}%`,
              transform: `translateX(${hover.xPct > 60 ? "-108%" : "8px"})`,
            }}
          >
            <div className="text-foreground">step {hover.step}</div>
            {hover.entries.map((e) => (
              <div key={e.label} className="flex items-center gap-1.5">
                <span
                  className="inline-block w-2.5 h-[3px] rounded-full shrink-0"
                  style={{ background: e.color }}
                  aria-hidden="true"
                />
                {e.label}: <b className="text-foreground">{e.alive}</b>
              </div>
            ))}
          </div>
        )}
      </div>
      {drawn.length > 1 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 font-mono text-[11px] text-muted-foreground">
          {drawn.map((s) => (
            <span className="inline-flex items-center gap-1.5" key={s.label}>
              <span
                className="inline-block w-2.5 h-[3px] rounded-full shrink-0"
                style={{ background: s.color }}
                aria-hidden="true"
              />
              {s.label}
            </span>
          ))}
        </div>
      )}
    </ChartFigure>
  );
}

// ---------------------------------------------------------------------------
// Actions-by-type horizontal breakdown (nominal categories -> one quiet hue).
// ---------------------------------------------------------------------------
function ActionsBreakdown({ counts }: { counts: Record<string, number> }) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <ChartFigure
      title="Actions by type"
      sub="what the swarm actually did, across every step"
    >
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No per-step action records in this run.
        </p>
      ) : (
        <div
          className="flex flex-col gap-2.5"
          role="img"
          aria-label="Action counts by type"
        >
          {rows.map(([type, n]) => (
            <div
              className="grid grid-cols-[minmax(70px,110px)_1fr_auto] items-center gap-3"
              key={type}
              title={`${type}: ${n}`}
            >
              <span className="font-mono text-xs text-muted-foreground truncate">
                {type.replace(/_/g, " ")}
              </span>
              <div className="h-2 rounded-full bg-surface overflow-hidden">
                <div
                  className="h-full rounded-full bg-idle/60"
                  style={{ width: `${(n / max) * 100}%` }}
                />
              </div>
              <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                {n}
              </span>
            </div>
          ))}
        </div>
      )}
    </ChartFigure>
  );
}

// ---------------------------------------------------------------------------
// Per-persona statistics table
// ---------------------------------------------------------------------------
function badgesFor(p: PersonaStats) {
  // Reuse the existing badge rendering: feed the declared perturbation kinds
  // through the same theme helper the tiles use.
  const cfg: PersonaConfig = {
    id: p.persona_id,
    name: p.persona_name,
    active_perturbations: p.perturbations,
  };
  return p.perturbations.length ? perturbationBadges(cfg) : [];
}

function PersonaStatsTable({ personas }: { personas: PersonaStats[] }) {
  return (
    <div>
      <h3 className="text-sm font-medium">Per-persona statistics</h3>
      <p className="text-xs text-muted-foreground mt-1 mb-3">
        One row per synthetic user — degraded channels, outcome, effort and
        friction signals.
      </p>
      <div className="gp-table-scroll">
        <table className="gp-table">
          <thead>
            <tr>
              <th>persona</th>
              <th>perturbations</th>
              <th>outcome</th>
              <th className="text-right">steps</th>
              <th className="text-right">duration</th>
              <th className="text-right">avg latency</th>
              <th className="text-right" title="Longest run of identical actions">
                rage clicks
              </th>
              <th
                className="text-right"
                title="Actions blocked by the policy gateway"
              >
                blocked
              </th>
            </tr>
          </thead>
          <tbody>
            {personas.map((p) => {
              const badges = badgesFor(p);
              return (
                <tr key={p.persona_id}>
                  <td className="font-medium whitespace-nowrap">
                    {p.persona_name}
                  </td>
                  <td className="font-mono text-[10px] text-muted-foreground">
                    {badges.length
                      ? badges.map((b) => b.text).join(" · ")
                      : "baseline"}
                  </td>
                  <td
                    className="whitespace-nowrap"
                    style={{ color: OUTCOME_COLOR[p.outcome] }}
                  >
                    {OUTCOME_LABELS[p.outcome]}
                  </td>
                  <td className="text-right font-mono text-xs tabular-nums">
                    {p.steps_survived}
                  </td>
                  <td className="text-right font-mono text-xs tabular-nums">
                    {fmtDuration(p.duration_s)}
                  </td>
                  <td className="text-right font-mono text-xs tabular-nums">
                    {fmtMs(p.avg_latency_ms)}
                  </td>
                  <td className="text-right font-mono text-xs tabular-nums">
                    {p.max_repeated_action >= 2 ? (
                      <span
                        style={{
                          color:
                            p.max_repeated_action >= 3
                              ? "var(--fail)"
                              : "var(--live)",
                        }}
                        title={`${p.max_repeated_action}× the same action in a row`}
                      >
                        ×{p.max_repeated_action}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="text-right font-mono text-xs tabular-nums">
                    {p.blocked_actions > 0 ? p.blocked_actions : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The dashboard
// ---------------------------------------------------------------------------
export function StatsPanel({ insights }: { insights: RunInsights }) {
  const stats = insights.stats;
  if (!stats) return null;
  const r = stats.run;
  const finished = r.personas_succeeded + r.personas_abandoned;
  const pct = finished
    ? Math.round((100 * r.personas_succeeded) / finished)
    : 0;
  const series = insights.survival_series ?? [];

  const tiles: {
    key: string;
    label: string;
    value: string;
    color?: string;
    title?: string;
  }[] = [
    {
      key: "completion",
      label: "completion",
      value: `${pct}%`,
      color: scoreColor(pct),
      title: `${r.personas_succeeded} of ${finished} non-error personas completed`,
    },
    {
      key: "avg",
      label: "avg Holo latency",
      value: fmtMs(r.avg_latency_ms),
      title: "Mean model round-trip per step",
    },
    {
      key: "p95",
      label: "p95 latency",
      value: fmtMs(r.p95_latency_ms),
      title: "95th percentile model round-trip",
    },
    { key: "steps", label: "total steps", value: String(r.total_steps) },
    {
      key: "dur",
      label: "total duration",
      value: fmtDuration(r.total_duration_s),
      title: "Sum of persona session durations",
    },
    ...(r.blocked_actions > 0
      ? [
          {
            key: "blocked",
            label: "policy-blocked",
            value: String(r.blocked_actions),
            title: "Actions blocked at the network layer by the NemoClaw policy",
          },
        ]
      : []),
    {
      key: "median",
      label: "median steps to abandon",
      value:
        r.median_steps_to_abandon != null
          ? String(r.median_steps_to_abandon)
          : "—",
    },
    {
      key: "fastest",
      label: "fastest success",
      value:
        r.fastest_success_steps != null
          ? `${r.fastest_success_steps} steps`
          : "—",
    },
  ];

  return (
    <div className="flex flex-col gap-10" aria-label="Run statistics">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-6">
        {tiles.map((t) => (
          <StatTile
            key={t.key}
            label={t.label}
            value={t.value}
            color={t.color}
            title={t.title}
          />
        ))}
      </div>

      {series.length > 0 && (
        <SurvivalStepChart
          title="Survival curve"
          sub="personas still in the flow at each step (step-after)"
          series={[{ label: "alive", color: SERIES_CURRENT, points: series }]}
        />
      )}
      <ActionsBreakdown counts={r.actions_by_type} />

      <PersonaStatsTable personas={stats.personas} />
    </div>
  );
}
