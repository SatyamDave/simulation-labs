// Client for the hosted /v2 API. Token-based auth: signup/login return a JWT we
// store and send as `Authorization: Bearer <jwt>` (sidesteps cross-origin cookie
// pain in dev). FROZEN — pages call these; do not change signatures.

import type {
  ApiKeyRow,
  AuthResult,
  Baseline,
  CreatedApiKey,
  MeResult,
  Project,
  RunReport,
  RunSummary2,
  TrendPoint,
} from "./types2";

// Same base-URL resolution as ../api.ts: explicit env > dev assumption > same-origin.
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  (import.meta.env.DEV ? "http://localhost:8000" : "");

const TOKEN_KEY = "sl_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function req<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- auth ----
export const signup = (email: string, password: string) =>
  req<AuthResult>("POST", "/v2/auth/signup", { email, password });
export const login = (email: string, password: string) =>
  req<AuthResult>("POST", "/v2/auth/login", { email, password });
export const logout = () => req<void>("POST", "/v2/auth/logout");
export const me = () => req<MeResult>("GET", "/v2/auth/me");

// ---- projects + keys ----
export const listProjects = () => req<Project[]>("GET", "/v2/projects");
export const createProject = (name: string) =>
  req<Project>("POST", "/v2/projects", { name });
export const getProject = (id: string) =>
  req<Project>("GET", `/v2/projects/${id}`);
export const listKeys = (projectId: string) =>
  req<ApiKeyRow[]>("GET", `/v2/projects/${projectId}/keys`);
export const createKey = (projectId: string, name: string) =>
  req<CreatedApiKey>("POST", `/v2/projects/${projectId}/keys`, { name });
export const revokeKey = (projectId: string, keyId: string) =>
  req<void>("DELETE", `/v2/projects/${projectId}/keys/${keyId}`);

// ---- runs / history / trend / baselines ----
export function listRuns(
  projectId: string,
  opts: { flow?: string; limit?: number; offset?: number } = {}
): Promise<RunSummary2[]> {
  const q = new URLSearchParams({ project_id: projectId });
  if (opts.flow) q.set("flow", opts.flow);
  if (opts.limit != null) q.set("limit", String(opts.limit));
  if (opts.offset != null) q.set("offset", String(opts.offset));
  return req<RunSummary2[]>("GET", `/v2/runs?${q.toString()}`);
}
export const getRun = (runId: string) =>
  req<RunSummary2>("GET", `/v2/runs/${runId}`);
export const getRunReport = (runId: string) =>
  req<RunReport>("GET", `/v2/runs/${runId}/report`);
export const getRunTrend = (runId: string, flow?: string) =>
  req<TrendPoint[]>(
    "GET",
    `/v2/runs/${runId}/trend${flow ? `?flow=${encodeURIComponent(flow)}` : ""}`
  );
export const getBaselines = (projectId: string, flow?: string) =>
  req<Baseline[]>(
    "GET",
    `/v2/projects/${projectId}/baselines${flow ? `?flow=${encodeURIComponent(flow)}` : ""}`
  );
export const setBaseline = (
  projectId: string,
  flowName: string,
  runId: string
) =>
  req<Baseline>("POST", `/v2/projects/${projectId}/baselines`, {
    flow_name: flowName,
    run_id: runId,
  });

// URL for a stored artifact via the AUTHED route (session cookie scopes access;
// the old open /artifacts mount was a cross-tenant IDOR — see security-audit.md).
// Accepts either a bare filename or a legacy "/artifacts/<run_id>/<path>" value and
// normalizes to /v2/runs/<run_id>/artifacts/<path>.
export function runArtifactUrl(runId: string, pathOrRel: string): string {
  let rel = pathOrRel.replace(/^\/+/, "");
  const legacy = `artifacts/${runId}/`;
  if (rel.startsWith(legacy)) rel = rel.slice(legacy.length);
  return `${API_BASE}/v2/runs/${runId}/artifacts/${rel}`;
}
