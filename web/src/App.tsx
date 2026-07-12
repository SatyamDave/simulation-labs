import { useCallback, useEffect, useState } from "react";
import { MotionConfig, motion } from "framer-motion";
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

function Loading({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-32 text-center text-sm font-mono text-muted-foreground">
      {children}
    </div>
  );
}

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
      <Loading>
        {connection === "error"
          ? "websocket error — is the orchestrator running?"
          : `waiting for the swarm on run ${runId}…`}
      </Loading>
    );
  }

  return (
    <div>
      <PersonaGrid state={state} />
      {state.status === "finished" && (
        <div className="mt-8 flex flex-wrap items-center gap-4 rounded-2xl border border-border bg-background p-6">
          <p className="text-xl font-light tabular-nums">
            Run finished
            {state.completionRate != null
              ? ` — ${Math.round(state.completionRate * 100)}% made it`
              : ""}
          </p>
          <span className="flex-1" />
          <motion.button
            className="px-8 py-3 bg-foreground text-background rounded-full font-medium"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onReport}
          >
            View the report
          </motion.button>
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

  if (error) return <Loading>could not load report — {error}</Loading>;
  if (!report) return <Loading>building the report…</Loading>;
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

/** Dark mode on a `.dark` html class; initial value set pre-paint in index.html. */
function useTheme(): { dark: boolean; toggle: () => void } {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
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

export default function App() {
  const [view, setView] = useState<View>({ kind: "launch" });
  const { dark, toggle } = useTheme();

  return (
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen bg-background text-foreground flex flex-col">
        <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-sm border-b border-border/40">
          <div className="container mx-auto px-6 py-4 max-w-5xl flex items-center justify-between gap-4">
            <div className="flex items-baseline gap-4 min-w-0">
              <button
                className="text-lg font-mono font-medium hover:opacity-70 transition-opacity whitespace-nowrap"
                onClick={() => setView({ kind: "launch" })}
                title="Back to launch"
              >
                [simulation labs]
              </button>
              <span className="hidden md:inline text-sm font-mono text-muted-foreground truncate">
                synthetic users that do, not say
              </span>
            </div>
            <nav className="flex items-center gap-4 sm:gap-6">
              <span className="hidden sm:inline text-sm font-mono text-muted-foreground">
                {CRUMB[view.kind]}
              </span>
              {view.kind !== "launch" && (
                <button
                  className="text-sm px-4 py-2 bg-foreground text-background rounded-full font-medium hover:opacity-90 transition-opacity"
                  onClick={() => setView({ kind: "launch" })}
                >
                  New run
                </button>
              )}
              <ThemeToggle dark={dark} toggle={toggle} />
            </nav>
          </div>
        </header>

        <main className="flex-1">
          {view.kind === "launch" && (
            <LaunchForm
              onLaunched={(runId) => setView({ kind: "live", runId })}
              onOfflineDemo={() => setView({ kind: "offline" })}
            />
          )}
          {view.kind !== "launch" && (
            <div className="container mx-auto max-w-5xl px-6 py-12">
              {view.kind === "live" && (
                <LiveRun
                  runId={view.runId}
                  onReport={() => setView({ kind: "report", runId: view.runId })}
                />
              )}
              {view.kind === "report" && <LiveReport runId={view.runId} />}
              {view.kind === "offline" && <OfflineDemo />}
            </div>
          )}
        </main>

        <footer className="border-t border-border/40 pt-12 pb-8 px-6">
          <div className="container mx-auto max-w-5xl">
            <div className="flex flex-col md:flex-row justify-between items-start gap-8 mb-10">
              <div>
                <span className="font-mono text-sm">[simulation labs]</span>
                <p className="text-sm text-muted-foreground mt-2 max-w-xs">
                  Synthetic users that do, not say. Point a swarm at your site
                  and get receipts.
                </p>
              </div>
            </div>
            <div className="border-t border-border/40 pt-6 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-muted-foreground">
              <p>© 2026 Simulation Labs, Inc.</p>
              <p>Survival curves, heatmaps, video receipts.</p>
            </div>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}
