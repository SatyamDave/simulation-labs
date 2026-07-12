// Selectable personas for the LaunchForm (live path). There is no GET /personas
// endpoint in the contract, so the frontend ships this catalog. The `id`s must
// match personas/*.json slugs on the backend (Agent 1) — confirm before the live
// demo. These eight mirror personas/*.json (baselines first).

import type { PersonaConfig, PerturbationKind } from "./types";

export interface CatalogEntry extends PersonaConfig {
  perturb: PerturbationKind[];
}

export const PERSONA_CATALOG: CatalogEntry[] = [
  {
    id: "power-user",
    name: "Alex (power user)",
    blurb: "Baseline — no impairment",
    perturb: [],
    active_perturbations: [],
  },
  {
    id: "ai-agent",
    name: "Agent (headless AI)",
    blurb: "Is your site agent-ready?",
    perturb: [],
    active_perturbations: [],
  },
  {
    id: "grandma-72",
    name: "Margaret, 72",
    blurb: "First-timer, presses the biggest button",
    perturb: ["low_literacy", "blur"],
    active_perturbations: ["low_literacy", "blur"],
  },
  {
    id: "low-vision",
    name: "Sam (low vision)",
    blurb: "Can't read small grey text",
    perturb: ["blur", "downscale"],
    active_perturbations: ["blur", "downscale"],
  },
  {
    id: "colorblind",
    name: "Jordan (deuteranopia)",
    blurb: "Red/green colour-blind — colour-only cues vanish",
    perturb: ["cvd"],
    active_perturbations: ["cvd"],
  },
  {
    id: "tremor",
    name: "Dev (hand tremor)",
    blurb: "Misses small tap targets",
    perturb: ["tremor"],
    active_perturbations: ["tremor"],
  },
  {
    id: "impatient-mobile",
    name: "Priya (impatient, mobile)",
    blurb: "Abandons after a few seconds",
    perturb: ["small_viewport", "impatience"],
    active_perturbations: ["small_viewport", "impatience"],
    viewport: { width: 390, height: 844 },
  },
  {
    id: "non-native",
    name: "Luca (non-native EN)",
    blurb: "Idiomatic labels and jargon slow him down",
    perturb: ["low_literacy", "impatience"],
    active_perturbations: ["low_literacy", "impatience"],
    language: "it",
  },
];
