import { useCallback, useState } from "react";
import { MotionConfig } from "framer-motion";
import { LaunchForm, type LaunchValues } from "./components/LaunchForm";
import { PersonaGrid } from "./components/PersonaGrid";
import { ReportView } from "./components/ReportView";
import { OfflineDemo } from "./components/OfflineDemo";
import { CompareView } from "./components/CompareView";
import { IndexView } from "./components/IndexView";
import { PolicyPanel } from "./components/PolicyPanel";
import { useRunStream } from "./useRunStream";
import { getReport, startRun } from "./api";
import type { RunReport } from "./types";

type Mode = "launch" | "live" | "report" | "offline" | "index" | "compare";

/** Dark mode on a `.dark` html class; initial value set pre-paint in index.html. */
function useTheme(): { dark: boolean; toggle: () => void } {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );
  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("theme", next ? "dark" : "light");
      return next;
    });
  }, []);
  return { dark, toggle };
}

function ThemeToggle({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-hover transition-colors"
    >
      {dark ? (
        /* sun */
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m9.9 9.9l1.4 1.4M3 12h2m14 0h2M5.6 18.4l1.4-1.4m9.9-9.9l1.4-1.4M16 12a4 4 0 11-8 0 4 4 0 018 0z"
          />
        </svg>
      ) : (
        /* moon */
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
          />
        </svg>
      )}
    </button>
  );
}

export default function App() {
  const [mode, setMode] = useState<Mode>("launch");
  const [runId, setRunId] = useState<string | null>(null);
  const [report, setReport] = useState<RunReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const { dark, toggle } = useTheme();

  const { state } = useRunStream(mode === "live" ? runId : null);

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
        )}). Try the offline demo — it needs no server.`
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
      setError(`Couldn't load the report: ${String(err)}`);
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
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen bg-background text-foreground flex flex-col">
        <header className="sticky top-0 z-50 bg-background border-b border-border">
          <div className="mx-auto max-w-6xl px-6 h-12 flex items-center justify-between">
            <button
              type="button"
              className="font-mono text-sm hover:opacity-70 transition-opacity"
              onClick={reset}
              title="Back to start"
            >
              simulation labs
            </button>
            <ThemeToggle dark={dark} toggle={toggle} />
          </div>
        </header>

        <main className="flex-1">
          {mode === "launch" && (
            <LaunchForm
              onLaunch={handleLaunch}
              onOfflineDemo={() => setMode("offline")}
              onIndex={() => setMode("index")}
              busy={busy}
              error={error}
            />
          )}

          {mode !== "launch" && (
            <div className="mx-auto max-w-6xl px-6 py-10">
              {mode === "offline" && <OfflineDemo onExit={reset} />}

              {mode === "index" && <IndexView onBack={reset} />}

              {mode === "live" && (
                <div className="flex flex-col gap-6">
                  {loadingReport && (
                    <p className="text-sm text-muted-foreground">
                      Loading the report…
                    </p>
                  )}
                  {error && <p className="text-sm text-fail">{error}</p>}
                  <PolicyPanel />
                  <PersonaGrid
                    state={state}
                    reportReady={state.status === "finished"}
                    onSeeReport={openLiveReport}
                  />
                </div>
              )}

              {mode === "report" && report && (
                <ReportView
                  report={report}
                  live
                  onBack={() => setMode("live")}
                  onCompare={() => setMode("compare")}
                />
              )}

              {mode === "compare" && report && (
                <CompareView
                  baseReport={report}
                  onBack={() => setMode("report")}
                />
              )}
            </div>
          )}
        </main>

        <footer className="border-t border-border mt-24 py-8 px-6">
          <div className="mx-auto max-w-6xl flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span className="font-mono">simulation labs</span>
            <span>Powered by H Company Holo &amp; Gradium · © 2026</span>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}
