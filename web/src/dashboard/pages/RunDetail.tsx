// Run-detail page for the hosted dashboard. Loads the stored run summary
// (getRun) + the generated RunReport (getRunReport), then shows the headline
// completion %, per-persona survival, the abandonment heatmap, links to stored
// artifacts, and a "set as baseline for <flow>" action. Reuses the demo's
// SurvivalCurve + Heatmap (their props fit a stored RunReport verbatim); the
// rest is a lightweight, self-contained view so we don't couple to the demo's
// ReportView (which fetches insights and is wired to the old /api client).

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth";
import * as api2 from "../api2";
import { ApiError } from "../api2";
import type { RunReport, RunSummary2 } from "../types2";
import type { PersonaResult } from "../../types";
import { OUTCOME_LABELS } from "../../types";
import { SurvivalCurve } from "../../components/SurvivalCurve";
import { Heatmap } from "../../components/Heatmap";

type LoadStatus = "loading" | "ready" | "processing" | "notfound" | "error";
type BaselineStatus =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const BACK_TO_RUNS = "/app/runs";

function Spinner({ label }: { label: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-24 text-muted-foreground"
      role="status"
      aria-live="polite"
    >
      <span
        className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-foreground"
        aria-hidden="true"
      />
      <span className="text-sm">{label}</span>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to={BACK_TO_RUNS}
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 rounded"
    >
      <span aria-hidden="true">←</span> Back to runs
    </Link>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <BackLink />
      <div className="mt-8 rounded-xl border border-border bg-card p-8">
        <h1 className="text-lg font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        <div className="mt-2 text-sm text-muted-foreground leading-relaxed">
          {children}
        </div>
      </div>
    </div>
  );
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { activeProject } = useAuth();

  const [status, setStatus] = useState<LoadStatus>("loading");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [summary, setSummary] = useState<RunSummary2 | null>(null);
  const [report, setReport] = useState<RunReport | null>(null);
  const [baseline, setBaseline] = useState<BaselineStatus>({ kind: "idle" });

  useEffect(() => {
    if (!runId) {
      setStatus("notfound");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setBaseline({ kind: "idle" });

    (async () => {
      // Summary first: it drives the "still processing" panel even when the
      // report isn't generated yet.
      let s: RunSummary2;
      try {
        s = await api2.getRun(runId);
        if (cancelled) return;
        setSummary(s);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setStatus("notfound");
          return;
        }
        setErrorMsg(
          err instanceof ApiError ? err.message : "Couldn't load this run."
        );
        setStatus("error");
        return;
      }

      try {
        const r = await api2.getRunReport(runId);
        if (cancelled) return;
        setReport(r);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        // 425 (and a not-yet-written 404 report) mean the run is still being
        // processed — the report artifact doesn't exist yet.
        if (
          err instanceof ApiError &&
          (err.status === 425 || err.status === 404)
        ) {
          setStatus("processing");
          return;
        }
        setErrorMsg(
          err instanceof ApiError ? err.message : "Couldn't load the report."
        );
        setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [runId]);

  const flowName = summary?.flow_name ?? "";

  const onSetBaseline = useCallback(async () => {
    if (!activeProject || !runId || !flowName) return;
    setBaseline({ kind: "saving" });
    try {
      await api2.setBaseline(activeProject.id, flowName, runId);
      setBaseline({ kind: "ok" });
    } catch (err) {
      setBaseline({
        kind: "error",
        message:
          err instanceof ApiError ? err.message : "Couldn't set the baseline.",
      });
    }
  }, [activeProject, runId, flowName]);

  if (status === "loading") return <Spinner label="Loading run…" />;

  if (status === "notfound") {
    return (
      <Panel title="Run not found">
        We couldn't find a run with that id. It may have been deleted, or the
        link is wrong.
      </Panel>
    );
  }

  if (status === "error") {
    return (
      <Panel title="Something went wrong">
        {errorMsg || "Couldn't load this run."} Please try again.
      </Panel>
    );
  }

  if (status === "processing") {
    return (
      <Panel title="Run still processing">
        <p>
          This run hasn't finished generating its report yet. Personas may still
          be walking the flow, or the receipts are being assembled. Check back
          in a moment.
        </p>
        {summary && (
          <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 font-mono text-xs">
            <dt className="text-muted-foreground">flow</dt>
            <dd className="text-foreground">{summary.flow_name}</dd>
            <dt className="text-muted-foreground">task</dt>
            <dd className="text-foreground break-words">{summary.task}</dd>
            <dt className="text-muted-foreground">target</dt>
            <dd className="text-foreground break-all">{summary.target_url}</dd>
            <dt className="text-muted-foreground">state</dt>
            <dd className="text-foreground">{summary.state}</dd>
          </dl>
        )}
      </Panel>
    );
  }

  // status === "ready" — report and summary are present.
  if (!report) return <Spinner label="Loading run…" />;

  const pct = Math.round((report.completion_rate ?? 0) * 100);
  const counted = report.survival.filter((s) => s.outcome !== "error");
  const survived = counted.filter((s) => s.completed).length;
  const total = counted.length;

  const nameOf = (id: string) =>
    report.survival.find((s) => s.persona_id === id)?.persona_name || id;

  const reportHtml = api2.artifactUrl(`/artifacts/${report.run_id}/report.html`);
  const targetShot = api2.artifactUrl(`/artifacts/${report.run_id}/target.png`);

  const resultsWithMedia = report.results.filter(
    (r) => r.video_path || r.audio_path
  );

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between gap-4">
        <BackLink />
        <a
          href={reportHtml}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 rounded"
        >
          Open full report.html ↗
        </a>
      </div>

      <header>
        <p
          className={`text-6xl md:text-7xl font-semibold tracking-tight tabular-nums leading-none ${
            pct > 50 ? "text-ok" : "text-fail"
          }`}
        >
          {pct}%
        </p>
        <h1 className="mt-6 text-2xl md:text-3xl font-semibold tracking-tight text-foreground">
          <span className="tabular-nums">
            {survived} of {total}
          </span>{" "}
          personas completed “{report.task}”
        </h1>
        <p className="mt-2 text-muted-foreground">
          <span className="tabular-nums">{total - survived}</span> abandoned the
          flow. Here is exactly where, and why.
        </p>
        <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-muted-foreground">
          {summary && (
            <span>
              flow{" "}
              <span className="text-foreground">{summary.flow_name}</span>
            </span>
          )}
          <span className="break-all">
            target <span className="text-foreground">{report.target_url}</span>
          </span>
        </dl>
      </header>

      {/* Set-as-baseline action */}
      <section className="mt-8 flex flex-wrap items-center gap-3 border-t border-border pt-6">
        <button
          type="button"
          onClick={onSetBaseline}
          disabled={
            !activeProject || !flowName || baseline.kind === "saving"
          }
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          {baseline.kind === "saving"
            ? "Setting baseline…"
            : `Set as baseline${flowName ? ` for ${flowName}` : ""}`}
        </button>
        {baseline.kind === "ok" && (
          <span className="text-sm text-ok" role="status">
            Baseline set for {flowName}.
          </span>
        )}
        {baseline.kind === "error" && (
          <span className="text-sm text-fail" role="alert">
            {baseline.message}
          </span>
        )}
        {!activeProject && (
          <span className="text-sm text-muted-foreground">
            Select a project to set a baseline.
          </span>
        )}
      </section>

      {/* Per-persona survival */}
      <section className="mt-10 border-t border-border pt-8">
        <h2 className="text-lg font-semibold text-foreground">
          Per-persona outcome
        </h2>
        <p className="mb-5 mt-1 text-sm text-muted-foreground">
          How far each persona got before finishing or giving up.
        </p>
        {report.survival.length ? (
          <SurvivalCurve survival={report.survival} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No per-persona survival recorded.
          </p>
        )}
      </section>

      {/* Abandonment heatmap */}
      <section className="mt-12 border-t border-border pt-8">
        <h2 className="text-lg font-semibold text-foreground">
          Where they gave up
        </h2>
        <p className="mb-5 mt-1 text-sm text-muted-foreground">
          Abandonment points on your actual page.
        </p>
        <Heatmap points={report.heatmap_points} liveBackdrop={targetShot} />
      </section>

      {/* Artifact links */}
      <section className="mt-12 border-t border-border pt-8">
        <h2 className="text-lg font-semibold text-foreground">Receipts</h2>
        <p className="mb-5 mt-1 text-sm text-muted-foreground">
          Stored video and cloned-voice exit-interview artifacts per persona.
        </p>
        {resultsWithMedia.length ? (
          <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">
            {resultsWithMedia.map((r: PersonaResult) => {
              const success = r.outcome === "success";
              return (
                <li
                  key={r.persona_id}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3"
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      success ? "bg-ok" : "bg-fail"
                    }`}
                    aria-hidden="true"
                  />
                  <span className="text-sm font-medium text-foreground">
                    {nameOf(r.persona_id)}
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {OUTCOME_LABELS[r.outcome].toLowerCase()}
                  </span>
                  <span className="ml-auto flex items-center gap-4">
                    {r.video_path && (
                      <a
                        href={api2.artifactUrl(r.video_path)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-muted-foreground underline underline-offset-2 transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 rounded"
                      >
                        video ↗
                      </a>
                    )}
                    {r.audio_path && (
                      <a
                        href={api2.artifactUrl(r.audio_path)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-muted-foreground underline underline-offset-2 transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 rounded"
                      >
                        interview ↗
                      </a>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No stored video or audio receipts for this run.
          </p>
        )}
      </section>
    </div>
  );
}
