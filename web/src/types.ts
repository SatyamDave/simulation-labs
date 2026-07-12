/**
 * TypeScript mirror of shared/ghostpanel_contracts/contracts.py (v1.0.0).
 * Field names are byte-faithful to the frozen Python contracts — if these
 * ever drift, contracts.py wins. Do not rename fields here.
 */

export const CONTRACT_VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// Enums (string literal unions — the wire values of the Python str Enums)
// ---------------------------------------------------------------------------
export type PerturbationKind =
  | "blur"
  | "downscale"
  | "cvd"
  | "tremor"
  | "small_viewport"
  | "impatience"
  | "low_literacy";

export type CVDType = "protan" | "deutan" | "tritan";

export type ActionType =
  | "click"
  | "write"
  | "scroll"
  | "go_back"
  | "refresh"
  | "wait"
  | "goto"
  | "restart"
  | "answer";

export type ScrollDirection = "up" | "down" | "left" | "right";

export type PersonaOutcome =
  | "success"
  | "step_budget"
  | "time_budget"
  | "stuck"
  | "error";

// ---------------------------------------------------------------------------
// Persona configuration
// ---------------------------------------------------------------------------
export interface Viewport {
  width: number; // default 1280
  height: number; // default 800
}

export interface PersonaConfig {
  id: string;
  name: string;
  blurb?: string;
  voice_id?: string | null;
  viewport?: Viewport;
  language?: string;
  blur_sigma?: number;
  downscale_factor?: number;
  cvd_type?: CVDType | null;
  cvd_severity?: number;
  tremor_sigma_px?: number;
  max_steps?: number;
  deadline_s?: number;
  literacy_note?: string;
  active_perturbations?: PerturbationKind[];
}

// ---------------------------------------------------------------------------
// Action + per-step / per-persona records
// ---------------------------------------------------------------------------
export interface Action {
  type: ActionType;
  x?: number | null;
  y?: number | null;
  text?: string | null;
  direction?: ScrollDirection | null;
  url?: string | null;
  seconds?: number | null;
  caption?: string;
  raw?: string;
}

export interface StepRecord {
  persona_id: string;
  step: number;
  action: Action;
  thumbnail_b64?: string;
  latency_ms?: number;
  note?: string;
}

export interface PersonaResult {
  persona_id: string;
  outcome: PersonaOutcome;
  steps?: StepRecord[];
  failure_coords?: [number, number] | null;
  failure_step?: number | null;
  failure_reason?: string;
  duration_s?: number;
  video_path?: string | null;
  transcript?: string;
  audio_path?: string | null;
}

// ---------------------------------------------------------------------------
// Report artifacts
// ---------------------------------------------------------------------------
export interface HeatPoint {
  x: number;
  y: number;
  weight?: number; // default 1.0
  persona_id?: string;
}

export interface SurvivalPoint {
  persona_id: string;
  persona_name?: string;
  outcome: PersonaOutcome;
  steps_survived: number;
  completed: boolean;
}

export interface RunReport {
  run_id: string;
  target_url: string;
  task: string;
  contract_version?: string;
  results?: PersonaResult[];
  survival?: SurvivalPoint[];
  heatmap_points?: HeatPoint[];
  completion_rate?: number;
  generated_at?: string;
}

// ---------------------------------------------------------------------------
// Event wire models — the exact JSON pushed over the WebSocket.
// Discriminated union on `event`.
// ---------------------------------------------------------------------------
export interface RunStarted {
  event: "run_started";
  run_id: string;
  target_url: string;
  task: string;
  personas: PersonaConfig[];
}

export interface PersonaStarted {
  event: "persona_started";
  run_id: string;
  persona_id: string;
}

export interface StepEvent {
  event: "step";
  run_id: string;
  persona_id: string;
  step: number;
  caption: string;
  thumbnail_b64?: string;
  x?: number | null;
  y?: number | null;
}

export interface PersonaFinished {
  event: "persona_finished";
  run_id: string;
  persona_id: string;
  outcome: PersonaOutcome;
  failure_coords?: [number, number] | null;
  failure_reason?: string;
  steps_survived?: number;
}

export interface RunFinished {
  event: "run_finished";
  run_id: string;
  report_url: string;
  completion_rate?: number;
}

export type RunEvent =
  | RunStarted
  | PersonaStarted
  | StepEvent
  | PersonaFinished
  | RunFinished;
