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
        <ReportView report={report} onBack={() => setMode("live")} />
      )}

      <footer className="app__foot">
        Ghostpanel · behavioral synthetic users · Holo × Gradium
      </footer>
    </div>
  );
}
