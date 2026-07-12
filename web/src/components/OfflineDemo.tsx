import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { RunEvent, RunReport } from "../types";
import { initialRunState, reduceEvent, type RunState } from "../useRunStream";
import PersonaGrid from "./PersonaGrid";
import ReportView from "./ReportView";

const TICK_MS = 1200; // one event per beat — slow enough to narrate on stage

function OfflineFlag() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs font-mono text-muted-foreground">
      offline replay · fixture data
    </span>
  );
}

function Loading({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-32 text-center text-sm font-mono text-muted-foreground">
      {children}
    </div>
  );
}

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
    return <Loading>could not load fixtures — {loadError}</Loading>;
  }
  if (!events) {
    return <Loading>loading fixtures…</Loading>;
  }

  if (showReport && report) {
    return (
      <div>
        <div className="flex flex-wrap items-center gap-4 mb-8">
          <OfflineFlag />
          <span className="flex-1" />
          <motion.button
            className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-2"
            whileHover={{ x: 5 }}
            onClick={() => {
              setShowReport(false);
              setReplayKey((k) => k + 1);
            }}
          >
            Replay the run
            <motion.span
              animate={{ x: [0, 5, 0] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              →
            </motion.span>
          </motion.button>
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
      <div className="mb-8">
        <OfflineFlag />
      </div>
      <PersonaGrid state={state} />
      {state.status === "finished" && (
        <div className="mt-8 flex flex-wrap items-center gap-4 rounded-2xl border border-border bg-background p-6">
          <p className="text-xl font-light tabular-nums">
            Run finished —{" "}
            {state.completionRate != null
              ? `${Math.round(state.completionRate * 100)}% made it`
              : "results in"}
          </p>
          <span className="flex-1" />
          <motion.button
            className="px-8 py-3 bg-foreground text-background rounded-full font-medium disabled:opacity-50"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowReport(true)}
            disabled={!report}
          >
            View the report
          </motion.button>
          <button
            className="px-4 py-3 text-sm text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setReplayKey((k) => k + 1)}
          >
            Replay
          </button>
        </div>
      )}
    </div>
  );
}
