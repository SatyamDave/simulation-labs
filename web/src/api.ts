// Ghostpanel API client. The backend base URL is read from VITE_API_BASE and
// never hardcoded. See CLAUDE.md for the endpoint contract.

import type { RunReport } from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";

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
  const wsBase = API_BASE.replace(/^http/, "ws");
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
