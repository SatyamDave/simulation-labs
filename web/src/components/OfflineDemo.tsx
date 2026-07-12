import { useEffect, useRef, useState } from "react";
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
      <div className="offline-error">
        <p>Couldn't load offline fixtures.</p>
        <pre>{loadError}</pre>
        <button className="btn btn--ghost" onClick={onExit}>
          ← Back
        </button>
      </div>
    );
  }

  if (view === "loading" || !report) {
    return <div className="offline-loading">Summoning the swarm…</div>;
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
    <div className="offline">
      <div className="offline__banner">
        <span className="offline__dot" /> OFFLINE DEMO — replaying local fixtures,
        no backend
        <button className="btn btn--ghost btn--sm offline__exit" onClick={onExit}>
          ✕ Exit
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
