// Types for the hosted dashboard (the /v2 API). Mirrors the Phase-2 backend
// (ghostpanel/store/models.py + server/routers/*). RunReport itself is reused
// from ../types (the contract mirror). FROZEN — pages import these.

import type { RunReport } from "../types";
export type { RunReport };

export type Tier = "free" | "team" | "audit";
export type RunState = "queued" | "running" | "finished" | "error";

export interface User {
  id: string;
  email: string;
}

export interface Project {
  id: string;
  name: string;
  tier: Tier;
  private_repos_enabled: boolean;
}

export interface ApiKeyRow {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
}

// Returned once at creation — the only time the full secret is visible.
export interface CreatedApiKey {
  key: ApiKeyRow;
  plaintext: string;
}

export interface RunSummary2 {
  id: string; // run_id
  project_id: string;
  state: RunState;
  target_url: string;
  task: string;
  flow_name: string;
  completion_rate?: number | null;
  created_at: string;
  finished_at?: string | null;
  persona_count?: number | null;
}

export interface EnqueuedRun {
  job_id: string;
  run_id?: string | null;
  status: string;
}

// One point on the "did this deploy make it worse" line.
export interface TrendPoint {
  created_at: string;
  completion_rate: number;
}

export interface Baseline {
  flow_name: string;
  run_id: string;
  completion_rate: number;
  created_at: string;
}

export interface AuthResult {
  user: User;
  project?: Project;
  token: string;
}

export interface MeResult {
  user: User;
  projects: Project[];
}
