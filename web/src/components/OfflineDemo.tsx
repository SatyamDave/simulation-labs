import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { LiveRunState, RunEvent, RunReport, Viewport } from "../types";
import { emptyLiveState, reduceEvent } from "../runReducer";
import { loadOfflineDemo } from "../offline";
import { PersonaGrid } from "./PersonaGrid";
import { ReportView } from "./ReportView";

// Offline coords were authored against the 640x480 sample screenshot.
const OFFLINE_SPACE: Viewport = { width: 640, height: 480 };

// Dramatic pacing per event type (ms before the NEXT event).
function delayFor(ev: RunEvent): number {
  switch (ev.event) {
    case "run_started":
      return 500;
    case "persona_started":
      return 220;
    case "step":
      return 360;
    case "persona_finished":
      return 700; // let each death land
    case "run_finished":
      return 400;
    default:
      return 300;
  }
}

interface Props {
  onExit: () => void;
}

export function OfflineDemo({ onExit }: Props) {
  const [state, setState] = useState<LiveRunState>(emptyLiveState());
  const [report, setReport] = useState<RunReport | null>(null);
  const [view, setView] = useState<"loading" | "grid" | "report">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadOfflineDemo()
      .then(({ timeline, report }) => {
        if (cancelled) return;
        setReport(report);
        setView("grid");

        let i = 0;
        const tick = () => {
          if (cancelled) return;
          if (i >= timeline.length) return;
          const ev = timeline[i];
          setState((prev) => reduceEvent(prev, ev));
          const d = delayFor(ev);
          i++;
          timerRef.current = window.setTimeout(tick, d);
        };
        tick();
      })
      .catch((err) => {
        if (!cancelled) setLoadError(String(err));
      });

    return () => {
      cancelled = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  if (loadError) {
    return (
      <div className="py-24 text-center">
        <p className="text-muted-foreground">Couldn't load offline fixtures.</p>
        <pre className="font-mono text-xs text-fail whitespace-pre-wrap max-w-xl mx-auto my-4 text-left">
          {loadError}
        </pre>
        <button
          type="button"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          onClick={onExit}
        >
          ← Back
        </button>
      </div>
    );
  }

  if (view === "loading" || !report) {
    return (
      <div className="py-24 text-center text-sm text-muted-foreground">
        Loading the simulation…
      </div>
    );
  }

  if (view === "report") {
    return (
      <ReportView
        report={report}
        coordSpace={OFFLINE_SPACE}
        onBack={() => setView("grid")}
      />
    );
  }

  const finished = state.status === "finished";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <motion.span
          className="w-1.5 h-1.5 rounded-full bg-live shrink-0"
          animate={{ opacity: [1, 0.35, 1] }}
          transition={{ duration: 1.6, repeat: Infinity }}
          aria-hidden="true"
        />
        <span>offline replay · local fixtures, no backend</span>
        <button
          type="button"
          className="ml-auto text-muted-foreground hover:text-foreground transition-colors"
          onClick={onExit}
        >
          exit
        </button>
      </div>
      <PersonaGrid
        state={state}
        coordSpace={OFFLINE_SPACE}
        reportReady={finished}
        onSeeReport={() => setView("report")}
      />
    </div>
  );
}
