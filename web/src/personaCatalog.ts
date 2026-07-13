// Static persona roster: the offline/backendless fallback for the LaunchForm
// (the live path prefers GET /personas) and the insights fallback's source of
// per-persona perturbation knowledge. The `id`s must match personas/*.json
// slugs on the backend (Agent 1). These eight mirror personas/*.json
// (baselines first).

import type { PersonaConfig } from "./types";

export const PERSONA_CATALOG: PersonaConfig[] = [
  {
    id: "power-user",
    name: "Alex (power user)",
    blurb: "Baseline — no impairment",
    active_perturbations: [],
    max_steps: 40,
    deadline_s: 240,
  },
  {
    id: "ai-agent",
    name: "Agent (headless AI)",
    blurb: "Is your site agent-ready?",
    active_perturbations: [],
    max_steps: 40,
    deadline_s: 240,
  },
  {
    id: "grandma-72",
    name: "Margaret, 72",
    blurb: "First-timer, presses the biggest button",
    active_perturbations: ["low_literacy", "blur"],
    blur_sigma: 1.6,
    max_steps: 20,
    deadline_s: 180,
  },
  {
    id: "low-vision",
    name: "Sam (low vision)",
    blurb: "Can't read small grey text",
    active_perturbations: ["blur", "downscale"],
    blur_sigma: 3.0,
    downscale_factor: 0.6,
    max_steps: 30,
    deadline_s: 150,
  },
  {
    id: "colorblind",
    name: "Jordan (deuteranopia)",
    blurb: "Red/green colour-blind — colour-only cues vanish",
    active_perturbations: ["cvd"],
    cvd_type: "deutan",
    cvd_severity: 0.9,
    max_steps: 30,
    deadline_s: 120,
  },
  {
    id: "tremor",
    name: "Dev (hand tremor)",
    blurb: "Misses small tap targets",
    active_perturbations: ["tremor"],
    tremor_sigma_px: 14.0,
    max_steps: 30,
    deadline_s: 150,
  },
  {
    id: "impatient-mobile",
    name: "Priya (impatient, mobile)",
    blurb: "Abandons after a few seconds",
    active_perturbations: ["small_viewport", "impatience"],
    viewport: { width: 390, height: 844 },
    max_steps: 15,
    deadline_s: 45,
  },
  {
    id: "non-native",
    name: "Luca (non-native EN)",
    blurb: "Idiomatic labels and jargon slow him down",
    active_perturbations: ["low_literacy", "impatience"],
    language: "it",
    max_steps: 20,
    deadline_s: 100,
  },
];
