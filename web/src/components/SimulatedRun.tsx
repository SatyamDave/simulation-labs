import { useEffect, useMemo, useRef, useState } from "react";
import type { LiveRunState, RunEvent, RunReport, Viewport } from "../types";
import { emptyLiveState, reduceEvent } from "../runReducer";
import { simulateRun } from "../sim/simulate";
import type { LaunchValues } from "./LaunchForm";
import { PersonaGrid } from "./PersonaGrid";
import { ReportView } from "./ReportView";

// Dramatic pacing per event type (ms before the NEXT event). Tuned so a full
// 8-persona run streams for ~90s of live grid, leaving room to walk the report —
// a comfortable ~2-minute screen recording. Each step lingers long enough for the
// caption to read on camera.
function delayFor(ev: RunEvent): number {
  switch (ev.event) {
    case "run_started":
      return 1000;
    case "persona_started":
      return 380;
    case "step":
      return 1300;
    case "persona_finished":
      return 1700; // let each death land
    case "run_finished":
      return 900;
    default:
      return 700;
  }
}

interface Props {
  values: LaunchValues;
  onExit: () => void;
}

// A simulated live run: identical UI/plumbing to a real backend run (same reducer,
// grid, report), but the RunEvent stream is generated in-browser from the operator's
// launch inputs. No "offline" chrome — it presents exactly as the real thing.
export function SimulatedRun({ values, onExit }: Props) {
  const { timeline, report, backdrop, coordSpace } = useMemo(
    () => simulateRun(values),
    [values]
  );

  const [state, setState] = useState<LiveRunState>(emptyLiveState());
  const [view, setView] = useState<"grid" | "report">("grid");
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState(emptyLiveState());

    let i = 0;
    const tick = () => {
      if (cancelled || i >= timeline.length) return;
      const ev = timeline[i];
      setState((prev) => reduceEvent(prev, ev));
      const d = delayFor(ev);
      i++;
      timerRef.current = window.setTimeout(tick, d);
    };
    // Small lead-in so the connecting → streaming transition reads on camera.
    timerRef.current = window.setTimeout(tick, 500);

    return () => {
      cancelled = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [timeline]);

  const finished = state.status === "finished";
  const space: Viewport = coordSpace;

  if (view === "report") {
    return (
      <ReportView
        report={report as RunReport}
        coordSpace={space}
        backdrop={backdrop}
        onBack={() => setView("grid")}
      />
    );
  }

  const connecting = state.status === "idle";
  const statusLabel = connecting
    ? "connecting"
    : finished
      ? "complete"
      : "streaming";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          onClick={onExit}
        >
          ← New run
        </button>
        <span className="inline-flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              finished ? "bg-ok" : "bg-live"
            }`}
            aria-hidden="true"
          />
          live · {statusLabel}
        </span>
      </div>
      <PersonaGrid
        state={state}
        coordSpace={space}
        backdrop={backdrop}
        reportReady={finished}
        onSeeReport={() => setView("report")}
      />
    </div>
  );
}
