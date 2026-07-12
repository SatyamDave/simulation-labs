// useRunStream(runId): open the live WebSocket, reduce RunEvents into per-persona
// live state. Returns the live state plus a connection status flag. When runId is
// null the hook is idle (used before a run is launched, and by the offline path).

import { useEffect, useRef, useState } from "react";
import { openRunSocket } from "./api";
import { emptyLiveState, reduceEvent } from "./runReducer";
import type { LiveRunState, RunEvent } from "./types";

export type WsStatus = "idle" | "connecting" | "open" | "closed" | "error";

export interface UseRunStream {
  state: LiveRunState;
  wsStatus: WsStatus;
}

export function useRunStream(runId: string | null): UseRunStream {
  const [state, setState] = useState<LiveRunState>(emptyLiveState());
  const [wsStatus, setWsStatus] = useState<WsStatus>("idle");
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) {
      setWsStatus("idle");
      return;
    }
    setState(emptyLiveState());
    setWsStatus("connecting");

    let closed = false;
    const ws = openRunSocket(runId);
    socketRef.current = ws;

    ws.onopen = () => {
      if (!closed) setWsStatus("open");
    };
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data as string) as RunEvent;
        setState((prev) => reduceEvent(prev, data));
      } catch (err) {
        // Ignore malformed frames rather than crash the grid.
        console.warn("[ghostpanel] bad WS frame", err);
      }
    };
    ws.onerror = () => {
      if (!closed) setWsStatus("error");
    };
    ws.onclose = () => {
      if (!closed) setWsStatus("closed");
    };

    return () => {
      closed = true;
      try {
        ws.close();
      } catch {
        /* noop */
      }
      socketRef.current = null;
    };
  }, [runId]);

  return { state, wsStatus };
}
