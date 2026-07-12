import { useEffect, useState } from "react";
import { getReport } from "./api";
import type { RunReport } from "./types";
import { useRunStream } from "./useRunStream";
import LaunchForm from "./components/LaunchForm";
import OfflineDemo from "./components/OfflineDemo";
import PersonaGrid from "./components/PersonaGrid";
import ReportView from "./components/ReportView";

type View =
  | { kind: "launch" }
  | { kind: "live"; runId: string }
  | { kind: "report"; runId: string }
  | { kind: "offline" };

/** Live run: WS-driven grid, then a hand-off to the report. */
function LiveRun({
  runId,
  onReport,
}: {
  runId: string;
  onReport: () => void;
}) {
  const { state, connection } = useRunStream(runId);

  if (connection === "connecting" || state.order.length === 0) {
    return (
      <div className="loading">
        {connection === "error"
          ? "websocket error — is the orchestrator running?"
          : `summoning the swarm for run ${runId}…`}
      </div>
    );
  }

  return (
    <div>
      <PersonaGrid state={state} />
      {state.status === "finished" && (
        <div className="finisbar">
          <span className="display">
            Run finished
            {state.completionRate != null
              ? ` — ${Math.round(state.completionRate * 100)}% made it`
              : ""}
          </span>
          <span className="runbar__spacer" />
          <button className="btn btn--primary" onClick={onReport}>
            View the report
          </button>
        </div>
      )}
    </div>
  );
}

/** Live report: fetched from GET /runs/{id}/report. */
function LiveReport({ runId }: { runId: string }) {
  const [report, setReport] = useState<RunReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReport(runId)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) return <div className="loading">could not load report — {error}</div>;
  if (!report) return <div className="loading">building the report…</div>;
  // No target-page screenshot in the report contract yet — the fixture
  // screenshot stands in as the heatmap backdrop.
  return (
    <ReportView report={report} screenshotUrl="/fixtures/sample_screenshot.png" />
  );
}

const CRUMB: Record<View["kind"], string> = {
  launch: "launch",
  live: "live run",
  report: "report",
  offline: "offline demo",
};

export default function App() {
  const [view, setView] = useState<View>({ kind: "launch" });

  return (
    <div className="shell">
      <header className="topbar">
        <button
          className="wordmark"
          onClick={() => setView({ kind: "launch" })}
          title="Back to launch"
        >
          Ghost<span className="wisp">panel</span>
        </button>
        <span className="tagline">synthetic users that do, not say</span>
        <span className="topbar__spacer" />
        <span className="crumb">{CRUMB[view.kind]}</span>
        {view.kind !== "launch" && (
          <button className="btn" onClick={() => setView({ kind: "launch" })}>
            New run
          </button>
        )}
      </header>

      <main>
        {view.kind === "launch" && (
          <LaunchForm
            onLaunched={(runId) => setView({ kind: "live", runId })}
            onOfflineDemo={() => setView({ kind: "offline" })}
          />
        )}
        {view.kind === "live" && (
          <LiveRun
            runId={view.runId}
            onReport={() => setView({ kind: "report", runId: view.runId })}
          />
        )}
        {view.kind === "report" && <LiveReport runId={view.runId} />}
        {view.kind === "offline" && <OfflineDemo />}
      </main>
    </div>
  );
}
