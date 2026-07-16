// Runs history + trend for the active project. Fetches the last 50 runs
// (optionally filtered to one flow), plots the completion trend across deploys
// at the top, and lists every run below.
//
// TREND-DATA APPROACH (documented per spec): rather than the extra
// `api2.getRunTrend(latestRunId)` round-trip, we derive the trend points
// CLIENT-SIDE from the runs we already fetched — finished runs with a non-null
// completion_rate, ordered oldest -> newest. This means the trend always
// respects the current flow filter for free (a per-flow trend) and needs no
// second request. `listRuns` returns newest-first, so we reverse for the chart.

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth";
import * as api2 from "../api2";
import { ApiError } from "../api2";
import type { RunSummary2 } from "../types2";
import { RunHistoryTable } from "../components/RunHistoryTable";
import { TrendChart } from "../components/TrendChart";

const ALL_FLOWS = ""; // sentinel: no flow filter

export default function Runs() {
  const { activeProject } = useAuth();
  const projectId = activeProject?.id ?? null;

  const [flow, setFlow] = useState<string>(ALL_FLOWS);
  const [runs, setRuns] = useState<RunSummary2[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Distinct flow names accumulated across fetches so the dropdown keeps all
  // options even while a single flow is selected.
  const [flowOptions, setFlowOptions] = useState<string[]>([]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api2
      .listRuns(projectId, { flow: flow || undefined, limit: 50 })
      .then((rows) => {
        if (cancelled) return;
        setRuns(rows);
        setFlowOptions((prev) => {
          const set = new Set(prev);
          for (const r of rows) if (r.flow_name) set.add(r.flow_name);
          return [...set].sort();
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setRuns(null);
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong loading runs."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, flow]);

  // Reset the flow filter when the project changes.
  useEffect(() => {
    setFlow(ALL_FLOWS);
    setFlowOptions([]);
  }, [projectId]);

  // Oldest -> newest, finished runs with a real completion rate only.
  const trendPoints = useMemo(() => {
    if (!runs) return [];
    return [...runs]
      .filter(
        (r) => r.state === "finished" && r.completion_rate != null
      )
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      )
      .map((r) => ({
        created_at: r.created_at,
        completion_rate: r.completion_rate as number,
      }));
  }, [runs]);

  // No project selected yet.
  if (!activeProject) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16 text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          No project selected
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Create or choose a project to see its run history.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Runs
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Completion across deploys for{" "}
            <span className="font-medium text-foreground">
              {activeProject.name}
            </span>
            .
          </p>
        </div>

        {flowOptions.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Flow</span>
            <select
              value={flow}
              onChange={(e) => setFlow(e.target.value)}
              className="rounded-md border border-border bg-card px-2 py-1.5 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value={ALL_FLOWS}>All flows</option>
              {flowOptions.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {loading && (
        <div className="flex items-center justify-center rounded-lg border border-border bg-card py-16 text-sm text-muted-foreground">
          <span
            className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-border border-t-foreground"
            aria-hidden
          />
          Loading runs…
        </div>
      )}

      {!loading && error && (
        <div
          role="alert"
          className="rounded-lg border border-border bg-card px-4 py-4 text-sm"
          style={{ color: "var(--fail)" }}
        >
          {error}
        </div>
      )}

      {!loading && !error && runs && runs.length === 0 && (
        <div className="rounded-lg border border-border bg-card px-6 py-14 text-center">
          <h2 className="text-base font-medium text-foreground">
            No runs yet
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            No runs yet — add the CI gate:{" "}
            <code className="rounded bg-hover px-1.5 py-0.5 font-mono text-xs text-foreground">
              sim gate
            </code>{" "}
            in your pipeline. See{" "}
            <code className="font-mono text-xs text-foreground">
              docs/ci.md
            </code>
            .
          </p>
        </div>
      )}

      {!loading && !error && runs && runs.length > 0 && (
        <div className="flex flex-col gap-8">
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-medium text-muted-foreground">
              Completion trend
            </h2>
            <TrendChart points={trendPoints} />
          </section>

          <section>
            <RunHistoryTable runs={runs} />
          </section>
        </div>
      )}
    </div>
  );
}
