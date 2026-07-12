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
  },
  {
    id: "ai-agent",
    name: "Agent (headless AI)",
    blurb: "Is your site agent-ready?",
    active_perturbations: [],
  },
  {
    id: "grandma-72",
    name: "Margaret, 72",
    blurb: "First-timer, presses the biggest button",
    active_perturbations: ["low_literacy", "blur"],
  },
  {
    id: "low-vision",
    name: "Sam (low vision)",
    blurb: "Can't read small grey text",
    active_perturbations: ["blur", "downscale"],
  },
  {
    id: "colorblind",
    name: "Jordan (deuteranopia)",
    blurb: "Red/green colour-blind — colour-only cues vanish",
    active_perturbations: ["cvd"],
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
    active_perturbations: ["small_viewport", "impatience"],
    viewport: { width: 390, height: 844 },
  },
  {
    id: "non-native",
    name: "Luca (non-native EN)",
    blurb: "Idiomatic labels and jargon slow him down",
    active_perturbations: ["low_literacy", "impatience"],
    language: "it",
  },
];
