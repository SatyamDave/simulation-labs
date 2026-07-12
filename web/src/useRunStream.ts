import { useEffect, useRef, useState } from "react";
import { openRunSocket } from "./api";
import type { PersonaConfig, PersonaOutcome, RunEvent } from "./types";

/** Live state for one persona tile, reduced from the RunEvent stream. */
export type TileStatus = "pending" | "running" | "success" | "dead" | "error";

export interface PersonaLive {
  persona: PersonaConfig;
  status: TileStatus;
  lastCaption: string;
  lastThumb: string; // data URI of the latest frame ("" = no signal yet)
  step: number;
  lastXY: [number, number] | null; // last action coords (viewport px)
  failure?: {
    outcome: PersonaOutcome;
    coords: [number, number] | null;
    reason: string;
    stepsSurvived: number;
  };
}

export interface RunState {
  runId: string | null;
  targetUrl: string;
  task: string;
  status: "idle" | "running" | "finished";
  order: string[]; // persona ids in run_started order
  personas: Record<string, PersonaLive>;
  completionRate: number | null;
  reportUrl: string | null;
}

export const initialRunState: RunState = {
  runId: null,
  targetUrl: "",
  task: "",
  status: "idle",
  order: [],
  personas: {},
  completionRate: null,
  reportUrl: null,
};

function freshTile(persona: PersonaConfig): PersonaLive {
  return {
    persona,
    status: "pending",
    lastCaption: "waiting for session…",
    lastThumb: "",
    step: 0,
    lastXY: null,
  };
}

function patchTile(
  state: RunState,
  personaId: string,
  update: (tile: PersonaLive) => Partial<PersonaLive>,
): RunState {
  const tile =
    state.personas[personaId] ?? freshTile({ id: personaId, name: personaId });
  const next = { ...tile, ...update(tile) };
  const order = state.personas[personaId]
    ? state.order
    : [...state.order, personaId];
  return {
    ...state,
    order,
    personas: { ...state.personas, [personaId]: next },
  };
}

/**
 * The single reducer for the RunEvent stream. Both the live WebSocket path
 * (useRunStream) and the offline fixture replay (OfflineDemo) go through it,
 * so the demo exercises exactly the code the real run uses.
 */
export function reduceEvent(state: RunState, ev: RunEvent): RunState {
  switch (ev.event) {
    case "run_started": {
      const personas: Record<string, PersonaLive> = {};
      for (const p of ev.personas) personas[p.id] = freshTile(p);
      return {
        ...initialRunState,
        runId: ev.run_id,
        targetUrl: ev.target_url,
        task: ev.task,
        status: "running",
        order: ev.personas.map((p) => p.id),
        personas,
      };
    }
    case "persona_started":
      return patchTile(state, ev.persona_id, () => ({
        status: "running",
        lastCaption: "session opened",
      }));
    case "step":
      return patchTile(state, ev.persona_id, (tile) => ({
        status: "running",
        step: ev.step,
        lastCaption: ev.caption,
        lastThumb: ev.thumbnail_b64 || tile.lastThumb,
        lastXY:
          ev.x != null && ev.y != null ? [ev.x, ev.y] : tile.lastXY,
      }));
    case "persona_finished": {
      const status: TileStatus =
        ev.outcome === "success"
          ? "success"
          : ev.outcome === "error"
            ? "error"
            : "dead";
      return patchTile(state, ev.persona_id, (tile) => ({
        status,
        step: Math.max(tile.step, ev.steps_survived ?? 0),
        failure:
          ev.outcome === "success"
            ? undefined
            : {
                outcome: ev.outcome,
                coords: ev.failure_coords ?? null,
                reason: ev.failure_reason ?? "",
                stepsSurvived: ev.steps_survived ?? 0,
              },
      }));
    }
    case "run_finished":
      return {
        ...state,
        status: "finished",
        completionRate: ev.completion_rate ?? null,
        reportUrl: ev.report_url,
      };
  }
}

export type ConnectionStatus = "idle" | "connecting" | "open" | "closed" | "error";

/**
 * Subscribe to WS /ws/runs/{runId} and reduce the event stream into live
 * per-persona state + a global run status.
 */
export function useRunStream(runId: string | null): {
  state: RunState;
  connection: ConnectionStatus;
} {
  const [state, setState] = useState<RunState>(initialRunState);
  const [connection, setConnection] = useState<ConnectionStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;
    setState(initialRunState);
    setConnection("connecting");
    const ws = openRunSocket(runId);
    wsRef.current = ws;

    ws.onopen = () => setConnection("open");
    ws.onmessage = (msg: MessageEvent<string>) => {
      try {
        const ev = JSON.parse(msg.data) as RunEvent;
        setState((s) => reduceEvent(s, ev));
      } catch (err) {
        console.error("ghostpanel: unparseable RunEvent", err, msg.data);
      }
    };
    ws.onerror = () => setConnection("error");
    ws.onclose = () => setConnection((c) => (c === "error" ? c : "closed"));

    return () => {
      wsRef.current = null;
      ws.close();
    };
  }, [runId]);

  return { state, connection };
}
