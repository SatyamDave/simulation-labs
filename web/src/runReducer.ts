// Pure reducer: fold a stream of RunEvents into per-persona live state.
// Shared by the live WebSocket hook (useRunStream) and the OfflineDemo replayer
// so both paths render identically.

import type {
  LiveRunState,
  PersonaLiveState,
  RunEvent,
} from "./types";

export function emptyLiveState(): LiveRunState {
  return {
    runId: null,
    targetUrl: "",
    task: "",
    status: "idle",
    order: [],
    personas: {},
    completionRate: 0,
    reportUrl: null,
  };
}

function asDataUri(thumb?: string): string {
  if (!thumb) return "";
  if (thumb.startsWith("data:") || thumb.startsWith("http")) return thumb;
  // Bare base64 -> assume JPEG data URI.
  return `data:image/jpeg;base64,${thumb}`;
}

export function reduceEvent(
  prev: LiveRunState,
  ev: RunEvent
): LiveRunState {
  switch (ev.event) {
    case "run_started": {
      const personas: Record<string, PersonaLiveState> = {};
      const order: string[] = [];
      for (const p of ev.personas) {
        order.push(p.id);
        personas[p.id] = {
          persona: p,
          status: "pending",
          lastCaption: "Waiting to be unleashed…",
          lastThumb: "",
          step: 0,
        };
      }
      return {
        ...emptyLiveState(),
        runId: ev.run_id,
        targetUrl: ev.target_url,
        task: ev.task,
        status: "running",
        order,
        personas,
      };
    }

    case "persona_started": {
      const cur = prev.personas[ev.persona_id];
      if (!cur) return prev;
      return {
        ...prev,
        personas: {
          ...prev.personas,
          [ev.persona_id]: {
            ...cur,
            status: "running",
            lastCaption: "Opening the page…",
          },
        },
      };
    }

    case "step": {
      const cur = prev.personas[ev.persona_id];
      if (!cur) return prev;
      // Never resurrect a finished tile from a late step event.
      if (cur.status === "success" || cur.status === "abandoned") return prev;
      return {
        ...prev,
        personas: {
          ...prev.personas,
          [ev.persona_id]: {
            ...cur,
            status: "running",
            step: ev.step,
            lastCaption: ev.caption || cur.lastCaption,
            lastThumb: asDataUri(ev.thumbnail_b64) || cur.lastThumb,
            x: ev.x ?? cur.x,
            y: ev.y ?? cur.y,
          },
        },
      };
    }

    case "persona_finished": {
      const cur = prev.personas[ev.persona_id];
      if (!cur) return prev;
      const success = ev.outcome === "success";
      // Prefer explicit failure_coords; else fall back to the last known click.
      const fallbackCoords: [number, number] | null =
        cur.x != null && cur.y != null
          ? [cur.x as number, cur.y as number]
          : null;
      return {
        ...prev,
        personas: {
          ...prev.personas,
          [ev.persona_id]: {
            ...cur,
            status: success ? "success" : "abandoned",
            failure: success
              ? undefined
              : {
                  outcome: ev.outcome,
                  coords: ev.failure_coords ?? fallbackCoords,
                  reason: ev.failure_reason || "",
                  stepsSurvived: ev.steps_survived ?? cur.step,
                },
          },
        },
      };
    }

    case "run_finished": {
      return {
        ...prev,
        status: "finished",
        completionRate: ev.completion_rate ?? prev.completionRate,
        reportUrl: ev.report_url,
      };
    }

    default:
      return prev;
  }
}

// Handy live tallies for the grid header.
export function tallies(state: LiveRunState) {
  const vals = Object.values(state.personas);
  const total = vals.length;
  const survived = vals.filter((p) => p.status === "success").length;
  const dead = vals.filter((p) => p.status === "abandoned").length;
  const running = vals.filter((p) => p.status === "running").length;
  const done = survived + dead;
  return { total, survived, dead, running, done };
}
