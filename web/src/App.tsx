import { useCallback, useState } from "react";
import { MotionConfig, motion } from "framer-motion";
import { LaunchForm, type LaunchValues } from "./components/LaunchForm";
import { PersonaGrid } from "./components/PersonaGrid";
import { ReportView } from "./components/ReportView";
import { OfflineDemo } from "./components/OfflineDemo";
import { useRunStream } from "./useRunStream";
import type { WsStatus } from "./useRunStream";
import { getReport, startRun } from "./api";
import type { RunReport } from "./types";

type Mode = "launch" | "live" | "report" | "offline";

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
      className="text-muted-foreground hover:text-foreground transition-colors"
    >
      {dark ? (
        /* sun */
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m9.9 9.9l1.4 1.4M3 12h2m14 0h2M5.6 18.4l1.4-1.4m9.9-9.9l1.4-1.4M16 12a4 4 0 11-8 0 4 4 0 018 0z"
          />
        </svg>
      ) : (
        /* moon */
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

const WS_LABEL: Record<WsStatus, string> = {
  idle: "idle",
  connecting: "connecting",
  open: "streaming",
  closed: "closed",
  error: "error",
};

function WsIndicator({ status }: { status: WsStatus }) {
  return (
    <span className="flex items-center gap-2">
      {status === "open" || status === "connecting" ? (
        <motion.span
          className={`w-2 h-2 rounded-full ${
            status === "open" ? "bg-emerald-500" : "bg-muted-foreground"
          }`}
          animate={{ scale: [1, 1.2, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      ) : (
        <span
          className={`w-2 h-2 rounded-full ${
            status === "idle" ? "bg-muted-foreground/40" : "bg-red-500"
          }`}
        />
      )}
      <span className="text-sm font-mono text-muted-foreground">
        live · {WS_LABEL[status]}
      </span>
    </span>
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
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen bg-background text-foreground flex flex-col">
        <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-sm border-b border-border/40">
          <div className="container mx-auto px-6 py-4 max-w-5xl flex items-center justify-between gap-4">
            <div className="flex items-baseline gap-4 min-w-0">
              <button
                type="button"
                className="text-lg font-mono font-medium hover:opacity-70 transition-opacity whitespace-nowrap"
                onClick={reset}
                title="Back to launch"
              >
                [simulation labs]
              </button>
              <span className="hidden md:inline text-sm font-mono text-muted-foreground truncate">
                behavioral user simulation
              </span>
            </div>
            <nav className="flex items-center gap-4 sm:gap-6">
              {mode !== "launch" && (
                <button
                  type="button"
                  className="text-sm px-4 py-2 bg-foreground text-background rounded-full font-medium hover:opacity-90 transition-opacity"
                  onClick={reset}
                >
                  New run
                </button>
              )}
              <ThemeToggle dark={dark} toggle={toggle} />
            </nav>
          </div>
        </header>

        <main className="flex-1">
          {mode === "launch" && (
            <LaunchForm
              onLaunch={handleLaunch}
              onOfflineDemo={() => setMode("offline")}
              busy={busy}
              error={error}
            />
          )}

          {mode !== "launch" && (
            <div className="container mx-auto max-w-5xl px-6 py-12">
              {mode === "offline" && <OfflineDemo onExit={reset} />}

              {mode === "live" && (
                <div className="flex flex-col gap-6">
                  <div className="flex items-center gap-6 flex-wrap">
                    <button
                      type="button"
                      className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                      onClick={reset}
                    >
                      ← New run
                    </button>
                    <WsIndicator status={wsStatus} />
                    {loadingReport && (
                      <span className="text-sm font-mono text-muted-foreground">
                        loading report…
                      </span>
                    )}
                  </div>
                  {error && (
                    <p className="text-sm text-red-500 border border-red-500/30 bg-red-500/5 rounded-2xl px-5 py-3">
                      {error}
                    </p>
                  )}
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
            </div>
          )}
        </main>

        <footer className="border-t border-border/40 pt-12 pb-8 px-6 mt-16">
          <div className="container mx-auto max-w-5xl">
            <div className="flex flex-col md:flex-row justify-between items-start gap-8 mb-10">
              <div>
                <span className="font-mono text-sm">[simulation labs]</span>
                <p className="text-sm text-muted-foreground mt-2 max-w-xs">
                  Behavioral user simulation. A swarm of impaired synthetic
                  users, and the exact pixel where they give up.
                </p>
              </div>
            </div>
            <div className="border-t border-border/40 pt-6 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-muted-foreground">
              <p>© 2026 Simulation Labs, Inc.</p>
              <p>Powered by H Company Holo &amp; Gradium</p>
            </div>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}
