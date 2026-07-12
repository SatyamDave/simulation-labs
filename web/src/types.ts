// TypeScript mirror of shared/ghostpanel_contracts/contracts.py.
// Re-declared here (never imported from Python). If these drift from the
// contract, contracts.py wins — keep them byte-faithful to field names.

// ---------------------------------------------------------------------------
// Enums (as string unions — the wire sends the string values)
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

// Only `success` counts as completion. `error` is infra failure (excluded from
// survival stats). Everything else is a genuine human abandon.
export type PersonaOutcome =
  | "success"
  | "step_budget"
  | "time_budget"
  | "stuck"
  | "error";

export const OUTCOME_LABELS: Record<PersonaOutcome, string> = {
  success: "Completed",
  step_budget: "Out of patience (steps)",
  time_budget: "Out of patience (time)",
  stuck: "Gave up (stuck)",
  error: "Infra error",
};

// ---------------------------------------------------------------------------
// Persona configuration
// ---------------------------------------------------------------------------
export interface Viewport {
  width: number;
  height: number;
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
// Action / step records
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
  weight?: number;
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
  results: PersonaResult[];
  survival: SurvivalPoint[];
  heatmap_points: HeatPoint[];
  completion_rate: number;
  generated_at?: string;
}

// ---------------------------------------------------------------------------
// Event wire models — discriminated union on `event`.
// This is the exact JSON pushed over the WebSocket.
// ---------------------------------------------------------------------------
export type EventType =
  | "run_started"
  | "persona_started"
  | "step"
  | "persona_finished"
  | "run_finished";

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

// ---------------------------------------------------------------------------
// Live-grid derived state (produced by useRunStream / the offline replayer)
// ---------------------------------------------------------------------------
export type TileStatus = "pending" | "running" | "success" | "abandoned";

export interface PersonaLiveState {
  persona: PersonaConfig;
  status: TileStatus;
  lastCaption: string;
  lastThumb: string; // data URI, or "" if none streamed yet
  step: number;
  // Steps whose caption started with "🛡" — blocked by the NemoClaw policy
  // gateway at the network layer. Drives the tile's shield badge counter.
  blockedSteps: number;
  x?: number | null;
  y?: number | null;
  failure?: {
    outcome: PersonaOutcome;
    coords?: [number, number] | null;
    reason: string;
    stepsSurvived: number;
  };
}

export type RunStatus = "idle" | "running" | "finished";

export interface LiveRunState {
  runId: string | null;
  targetUrl: string;
  task: string;
  status: RunStatus;
  order: string[]; // persona ids in launch order
  personas: Record<string, PersonaLiveState>;
  completionRate: number;
  reportUrl: string | null;
}
