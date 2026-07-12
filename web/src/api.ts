import type { PersonaConfig, RunReport } from "./types";

/** API base — never hardcoded in components. Set VITE_API_BASE to override. */
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000";

const WS_BASE = API_BASE.replace(/^http/, "ws");

export interface StartRunRequest {
  target_url: string;
  task: string;
  persona_ids: string[];
}

/** POST /runs → run_id */
export async function startRun(req: StartRunRequest): Promise<string> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`POST /runs failed (${res.status})`);
  const data = (await res.json()) as { run_id?: string; id?: string };
  const runId = data.run_id ?? data.id;
  if (!runId) throw new Error("POST /runs returned no run_id");
  return runId;
}

/** GET /runs/{id}/report */
export async function getReport(runId: string): Promise<RunReport> {
  const res = await fetch(`${API_BASE}/runs/${runId}/report`);
  if (!res.ok) throw new Error(`GET /runs/${runId}/report failed (${res.status})`);
  return (await res.json()) as RunReport;
}

/** WS /ws/runs/{id} — the RunEvent stream. */
export function openRunSocket(runId: string): WebSocket {
  return new WebSocket(`${WS_BASE}/ws/runs/${runId}`);
}

/** Resolve a server-relative artifact path ("artifacts/<run>/x.webm") to a URL. */
export function artifactUrl(path: string): string {
  if (/^(https?:)?\/\//.test(path)) return path;
  return `${API_BASE}/${path.replace(/^\//, "")}`;
}

/**
 * The demo swarm — used when the backend has no GET /personas (or is offline)
 * so the launch form always has a roster. Mirrors fixtures/events.jsonl.
 */
export const DEFAULT_PERSONAS: PersonaConfig[] = [
  {
    id: "grandma-72",
    name: "Margaret, 72",
    blurb: "First-timer, expects the biggest button to be the answer",
    active_perturbations: ["low_literacy", "impatience"],
  },
  {
    id: "low-vision",
    name: "Sam (low vision)",
    blurb: "Can't read small grey text",
    active_perturbations: ["blur", "downscale"],
  },
  {
    id: "tremor",
    name: "Dev (hand tremor)",
    blurb: "Misses small tap targets",
    active_perturbations: ["tremor"],
  },
  {
    id: "impatient-mobile",
    name: "Priya (impatient, mobile)",
    blurb: "Abandons after a few seconds",
    active_perturbations: ["impatience", "small_viewport"],
  },
  {
    id: "power-user",
    name: "Alex (power user)",
    blurb: "Baseline",
    active_perturbations: [],
  },
  {
    id: "ai-agent",
    name: "Agent (headless AI)",
    blurb: "Is your site agent-ready?",
    active_perturbations: [],
  },
];

/** GET /personas with a graceful fallback to the demo roster. */
export async function listPersonas(): Promise<PersonaConfig[]> {
  try {
    const res = await fetch(`${API_BASE}/personas`);
    if (res.ok) {
      const data = (await res.json()) as PersonaConfig[];
      if (Array.isArray(data) && data.length > 0) return data;
    }
  } catch {
    // backend offline — fall through to the demo roster
  }
  return DEFAULT_PERSONAS;
}
