import { useEffect, useRef, useState } from "react";
import type { RunEvent, RunReport } from "../types";
import { initialRunState, reduceEvent, type RunState } from "../useRunStream";
import PersonaGrid from "./PersonaGrid";
import ReportView from "./ReportView";

const TICK_MS = 1200; // one event per beat — slow enough to narrate on stage

/**
 * The guaranteed no-backend demo: replays web/public/fixtures/events.jsonl on
 * a timer through the SAME reducer the live WebSocket path uses, then renders
 * fixtures/run.json in ReportView with the heatmap over the sample screenshot.
 */
export default function OfflineDemo() {
  const [events, setEvents] = useState<RunEvent[] | null>(null);
  const [state, setState] = useState<RunState>(initialRunState);
  const [report, setReport] = useState<RunReport | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [replayKey, setReplayKey] = useState(0);
  const cursor = useRef(0);

  // load fixtures once
  useEffect(() => {
    fetch("/fixtures/events.jsonl")
      .then((r) => {
        if (!r.ok) throw new Error(`fixtures/events.jsonl → ${r.status}`);
        return r.text();
      })
      .then((text) => {
        const evs = text
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .map((line) => JSON.parse(line) as RunEvent);
        setEvents(evs);
      })
      .catch((err) => setLoadError(String(err)));
    fetch("/fixtures/run.json")
      .then((r) => {
        if (!r.ok) throw new Error(`fixtures/run.json → ${r.status}`);
        return r.json();
      })
      .then((data) => setReport(data as RunReport))
      .catch((err) => setLoadError(String(err)));
  }, []);

  // replay the stream, one event per tick, through the shared reducer
  useEffect(() => {
    if (!events) return;
    cursor.current = 0;
    setState(initialRunState);
    setShowReport(false);
    const timer = setInterval(() => {
      const ev = events[cursor.current];
      if (!ev) {
        clearInterval(timer);
        return;
      }
      cursor.current += 1;
      setState((s) => reduceEvent(s, ev));
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [events, replayKey]);

  if (loadError) {
    return <div className="loading">could not load fixtures — {loadError}</div>;
  }
  if (!events) {
    return <div className="loading">loading séance fixtures…</div>;
  }

  if (showReport && report) {
    return (
      <div>
        <div className="runbar" style={{ marginBottom: 4 }}>
          <span className="offline-flag">offline replay · fixture data</span>
          <span className="runbar__spacer" />
          <button
            className="btn"
            onClick={() => {
              setShowReport(false);
              setReplayKey((k) => k + 1);
            }}
          >
            ↺ Replay the run
          </button>
        </div>
        <ReportView
          report={report}
          screenshotUrl="/fixtures/sample_screenshot.png"
          offline
        />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <span className="offline-flag">offline replay · fixture data</span>
      </div>
      <PersonaGrid state={state} />
      {state.status === "finished" && (
        <div className="finisbar">
          <span className="display">
            Run finished —{" "}
            {state.completionRate != null
              ? `${Math.round(state.completionRate * 100)}% made it`
              : "results in"}
          </span>
          <span className="runbar__spacer" />
          <button
            className="btn btn--primary"
            onClick={() => setShowReport(true)}
            disabled={!report}
          >
            View the report
          </button>
          <button className="btn" onClick={() => setReplayKey((k) => k + 1)}>
            ↺ Replay
          </button>
        </div>
      )}
    </div>
  );
}
