// Static persona roster: the offline/backendless fallback for the LaunchForm
// (the live path prefers GET /personas) and the insights fallback's source of
// per-persona perturbation knowledge. The `id`s must match personas/*.json
// slugs on the backend. These five mirror the public personas/*.json roster:
// four behavioral segments plus the Fluent baseline (baseline first). The
// accessibility personas (low-vision, colorblind, ...) are retired to
// personas/_advanced/ — the mechanical capabilities remain in the engine.

import type { PersonaConfig } from "./types";

export const PERSONA_CATALOG: PersonaConfig[] = [
  {
    id: "fluent",
    name: "Fluent",
    blurb: "Baseline — patient, precise, fluent",
    active_perturbations: [],
    max_steps: 40,
    deadline_s: 240,
  },
  {
    id: "rushed",
    name: "Rushed",
    blurb: "In a hurry — bails when a step isn't obvious",
    active_perturbations: ["impatience"],
    max_steps: 10,
    deadline_s: 60,
  },
  {
    id: "misclick-prone",
    name: "Misclick-prone",
    blurb: "Clicks land off-target, misses small controls",
    active_perturbations: ["tremor"],
    tremor_sigma_px: 14.0,
    max_steps: 30,
    deadline_s: 150,
  },
  {
    id: "first-timer",
    name: "First-timer",
    blurb: "Reads literally, parses slowly, times out",
    active_perturbations: ["low_literacy", "impatience"],
    max_steps: 20,
    deadline_s: 150,
  },
  {
    id: "mobile-thumb",
    name: "Mobile-thumb",
    blurb: "Phone + thumb — small viewport, fat-finger taps",
    active_perturbations: ["small_viewport", "tremor"],
    tremor_sigma_px: 10.0,
    viewport: { width: 390, height: 844 },
    max_steps: 20,
    deadline_s: 120,
  },
];
