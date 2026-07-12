import { useState } from "react";
import { LaunchForm, type LaunchValues } from "./components/LaunchForm";
import { PersonaGrid } from "./components/PersonaGrid";
import { ReportView } from "./components/ReportView";
import { OfflineDemo } from "./components/OfflineDemo";
import { useRunStream } from "./useRunStream";
import { getReport, startRun } from "./api";
import type { RunReport } from "./types";

type Mode = "launch" | "live" | "report" | "offline";

export default function App() {
  const [mode, setMode] = useState<Mode>("launch");
  const [runId, setRunId] = useState<string | null>(null);
  const [report, setReport] = useState<RunReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const { state, wsStatus } = useRunStream(mode === "live" ? runId : null);

  async function handleLaunch(v: LaunchValues) {
    setError(null);
    setBusy(true);
    try {
      const { run_id } = await startRun(v);
      setRunId(run_id);
      setReport(null);
      setMode("live");
    } catch (err) {
      setError(
        `Couldn't reach the backend (${String(
          err
        )}). Try the Offline demo — it needs no server.`
      );
    } finally {
      setBusy(false);
    }
  }

  async function openLiveReport() {
    if (!runId) return;
    setLoadingReport(true);
    try {
      const r = await getReport(runId);
      setReport(r);
      setMode("report");
    } catch (err) {
      setError(`Couldn't load report: ${String(err)}`);
    } finally {
      setLoadingReport(false);
    }
  }

  function reset() {
    setMode("launch");
    setRunId(null);
    setReport(null);
    setError(null);
  }

  return (
    <div className="app">
      <div className="brandbar">
        <svg
          className="brandbar__mark"
          viewBox="0 0 32 32"
          aria-hidden="true"
          xmlns="http://www.w3.org/2000/svg"
        >
          <rect width="32" height="32" rx="8" fill="#12141c" />
          <circle
            cx="16"
            cy="16"
            r="9.5"
            fill="none"
            stroke="#7c8cff"
            strokeWidth="2"
            opacity="0.45"
          />
          <circle cx="16" cy="16" r="4" fill="#7c8cff" />
        </svg>
        <span className="brandbar__word">
          Simulation <b>Labs</b>
        </span>
        <span className="brandbar__tag">Behavioral User Simulation</span>
      </div>

      {mode === "launch" && (
        <LaunchForm
          onLaunch={handleLaunch}
          onOfflineDemo={() => setMode("offline")}
          busy={busy}
          error={error}
        />
      )}

      {mode === "offline" && <OfflineDemo onExit={reset} />}

      {mode === "live" && (
        <div className="live">
          <div className="live__bar">
            <button className="btn btn--ghost btn--sm" onClick={reset}>
              ← New run
            </button>
            <span className={`ws ws--${wsStatus}`}>
              <span className="ws__dot" /> live · {wsStatus}
            </span>
            {loadingReport && <span className="live__loading">loading report…</span>}
          </div>
          {error && <div className="launch__error live__error">⚠ {error}</div>}
          <PersonaGrid
            state={state}
            reportReady={state.status === "finished"}
            onSeeReport={openLiveReport}
          />
        </div>
      )}

      {mode === "report" && report && (
        <ReportView report={report} live onBack={() => setMode("live")} />
      )}

      <footer className="app__foot">
        <b>Simulation Labs</b> · Behavioral user simulation · Powered by
        H&nbsp;Company Holo &amp; Gradium
      </footer>
    </div>
  );
}
