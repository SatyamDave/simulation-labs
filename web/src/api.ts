// Ghostpanel API client. The backend base URL is read from VITE_API_BASE and
// never hardcoded. See CLAUDE.md for the endpoint contract.

import type { PersonaConfig, RunReport } from "./types";

// Default: explicit env override > dev-server assumption (backend on :8000) >
// same-origin ("" — the built app is mounted at / by the backend itself).
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  (import.meta.env.DEV ? "http://localhost:8000" : "");

export interface StartRunPayload {
  target_url: string;
  task: string;
  persona_ids: string[];
}

export interface StartRunResponse {
  run_id: string;
}

// POST /runs -> { run_id }
export async function startRun(
  payload: StartRunPayload
): Promise<StartRunResponse> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`startRun failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as StartRunResponse;
}

// GET /runs/{id}/report -> RunReport
export async function getReport(runId: string): Promise<RunReport> {
  const res = await fetch(`${API_BASE}/runs/${runId}/report`);
  if (!res.ok) {
    throw new Error(`getReport failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as RunReport;
}

// WS /ws/runs/{id} — the live RunEvent stream for the grid.
export function openRunSocket(runId: string): WebSocket {
  // Relative WS URLs are invalid — derive same-origin ws base when API_BASE is "".
  const wsBase = API_BASE
    ? API_BASE.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  return new WebSocket(`${wsBase}/ws/runs/${runId}`);
}

// Resolve an artifact path (e.g. "artifacts/<run>/x.webm" or "/artifacts/...")
// against the backend, so <video>/<audio> src load from the API host.
export function artifactUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//.test(path)) return path;
  const clean = path.replace(/^\/+/, "");
  // The report may store "artifacts/..." — the API serves them under /artifacts.
  const withPrefix = clean.startsWith("artifacts/") ? `/${clean}` : `/${clean}`;
  return `${API_BASE}${withPrefix}`;
}

/** GET /personas — the live roster. Returns null when the backend is
 * unreachable or empty so callers can fall back to the static catalog. */
export async function listPersonas(): Promise<PersonaConfig[] | null> {
  try {
    const res = await fetch(`${API_BASE}/personas`);
    if (!res.ok) return null;
    const data = (await res.json()) as PersonaConfig[];
    return Array.isArray(data) && data.length > 0 ? data : null;
  } catch {
    return null;
  }
}
