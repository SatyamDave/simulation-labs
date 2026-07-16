// Run history table — one row per stored run, newest first, each row a link
// into the run detail. Quiet functional styling: state is a small colored pill
// (green finished / orange running / neutral queued / red error), numbers use
// tabular-nums so the completion column doesn't jitter.

import { Link } from "react-router-dom";
import type { RunState, RunSummary2 } from "../types2";

interface RunHistoryTableProps {
  runs: RunSummary2[];
}

// state -> { label, functional color var }. `error` is infra failure, kept
// neutral so it never reads as a human abandonment.
const STATE_META: Record<RunState, { label: string; color: string }> = {
  finished: { label: "finished", color: "var(--ok)" },
  running: { label: "running", color: "var(--live)" },
  queued: { label: "queued", color: "var(--idle)" },
  error: { label: "error", color: "var(--fail)" },
};

function StatePill({ state }: { state: RunState }) {
  const meta = STATE_META[state] ?? { label: state, color: "var(--idle)" };
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{ color: meta.color, borderColor: meta.color }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: meta.color }}
        aria-hidden
      />
      {meta.label}
    </span>
  );
}

function completionText(rate?: number | null): string {
  if (rate == null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

// Compact relative time ("just now", "3h ago", "2d ago"), falling back to a
// date for anything older than a week. Local, dependency-free.
function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(then).toLocaleDateString();
}

export function RunHistoryTable({ runs }: RunHistoryTableProps) {
  if (runs.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No runs match this filter.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">State</th>
            <th className="px-4 py-2.5 font-medium">Completion</th>
            <th className="px-4 py-2.5 font-medium">Flow</th>
            <th className="px-4 py-2.5 font-medium">Target</th>
            <th className="px-4 py-2.5 font-medium">When</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              className="group border-b border-border last:border-0 transition-colors hover:bg-hover"
            >
              <td className="px-4 py-2.5">
                <Link
                  to={`/app/runs/${run.id}`}
                  className="inline-block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full"
                >
                  <StatePill state={run.state} />
                </Link>
              </td>
              <td className="px-4 py-2.5 tabular-nums">
                <Link
                  to={`/app/runs/${run.id}`}
                  className="text-foreground hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {completionText(run.completion_rate)}
                </Link>
              </td>
              <td className="px-4 py-2.5">
                <Link
                  to={`/app/runs/${run.id}`}
                  className="font-mono text-xs text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {run.flow_name}
                </Link>
              </td>
              <td className="max-w-[220px] px-4 py-2.5">
                <Link
                  to={`/app/runs/${run.id}`}
                  title={run.target_url}
                  className="block truncate text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {hostOf(run.target_url)}
                </Link>
              </td>
              <td className="whitespace-nowrap px-4 py-2.5 text-muted-foreground">
                <Link
                  to={`/app/runs/${run.id}`}
                  title={new Date(run.created_at).toLocaleString()}
                  className="tabular-nums hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {timeAgo(run.created_at)}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
