// Simulation Labs palette. Refined enterprise-dark surface (Linear / Vercel /
// Stripe register). Colors are the validated dark-mode steps from the dataviz
// reference palette (colorblind-safe, checked against a dark surface). Outcomes
// use the reserved STATUS palette (state, not identity); personas use the
// categorical palette (identity).

import type { PersonaConfig, PersonaOutcome, PerturbationKind } from "./types";

// Surfaces / ink (dark mode)
export const SURFACE = "#101218";
export const SURFACE_RAISED = "#171a22";
export const PLANE = "#090a0e";
export const INK = "#f4f5f8";
export const INK_2 = "#b3b8c4";
export const INK_MUTED = "#757b8a";
export const HAIRLINE = "rgba(255,255,255,0.08)";
export const GRID = "#242833";

// Categorical (identity) — dark-mode steps, fixed order, never cycled.
export const CATEGORICAL = [
  "#3987e5", // blue
  "#199e70", // aqua
  "#c98500", // yellow
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
  "#d55181", // magenta
  "#d95926", // orange
] as const;

// Status (state) — reserved, never themed. Outcomes map here.
export const STATUS = {
  good: "#22b364",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#e5484d",
  neutral: "#757b8a",
} as const;

// Outcome -> status color. success is the only "good" outcome.
export const OUTCOME_COLOR: Record<PersonaOutcome, string> = {
  success: STATUS.good,
  step_budget: STATUS.warning,
  time_budget: STATUS.serious,
  stuck: STATUS.critical,
  error: STATUS.neutral,
};

// Brand accent (single, confident) + the reserved fail red used on the heatmap.
export const ACCENT = "#7c8cff";
export const GHOST = ACCENT; // retained export name; now the brand accent
export const BLOOD = "#e5484d";

export function personaColor(index: number): string {
  return CATEGORICAL[index % CATEGORICAL.length];
}

// ---------------------------------------------------------------------------
// Perturbation badges — the "which channels are degraded" chips on a tile.
// Prefer the persona's declared active_perturbations; if absent (sparse
// fixtures only carry id/name/blurb), infer from the numeric fields, then
// fall back to id keywords so the offline demo still shows meaningful badges.
// ---------------------------------------------------------------------------
export interface Badge {
  icon: string;
  label: string;
  kind: PerturbationKind;
}

const BADGE_META: Record<PerturbationKind, { icon: string; label: string }> = {
  blur: { icon: "👁️", label: "Low vision (blur)" },
  downscale: { icon: "🔍", label: "Low acuity" },
  cvd: { icon: "🎨", label: "Color-vision deficiency" },
  tremor: { icon: "✋", label: "Hand tremor" },
  small_viewport: { icon: "📱", label: "Small viewport" },
  impatience: { icon: "⏱️", label: "Impatient" },
  low_literacy: { icon: "📖", label: "Low digital literacy" },
};

export function perturbationBadges(p: PersonaConfig): Badge[] {
  const kinds = new Set<PerturbationKind>();

  if (p.active_perturbations && p.active_perturbations.length) {
    for (const k of p.active_perturbations) kinds.add(k);
  } else {
    if ((p.blur_sigma ?? 0) > 0) kinds.add("blur");
    if ((p.downscale_factor ?? 1) < 1) kinds.add("downscale");
    if (p.cvd_type) kinds.add("cvd");
    if ((p.tremor_sigma_px ?? 0) > 0) kinds.add("tremor");
    if (p.viewport && p.viewport.width < 500) kinds.add("small_viewport");
    if (p.literacy_note) kinds.add("low_literacy");
  }

  // Keyword fallback (sparse fixtures) so tiles are never blank.
  if (kinds.size === 0) {
    const hay = `${p.id} ${p.name} ${p.blurb ?? ""}`.toLowerCase();
    if (/vision|blur|blind|sight|squint/.test(hay)) kinds.add("blur");
    if (/tremor|hand|shak|parkinson/.test(hay)) kinds.add("tremor");
    if (/color|colour|cvd|deuter|protan|tritan/.test(hay)) kinds.add("cvd");
    if (/mobile|cracked|phone|small/.test(hay)) kinds.add("small_viewport");
    if (/impatient|hurry|rush|quick/.test(hay)) kinds.add("impatience");
    if (/grandma|grandpa|first|literacy|elder|senior|\b7\d\b/.test(hay)) {
      kinds.add("low_literacy");
    }
  }

  return [...kinds].map((k) => ({ kind: k, ...BADGE_META[k] }));
}

// CSS filter that visually hints a persona's perception impairment on the tile
// thumbnail (offline demo has no real perturbed frames — this fakes the feel).
export function perceptionFilter(p: PersonaConfig): string | undefined {
  const badges = perturbationBadges(p).map((b) => b.kind);
  const parts: string[] = [];
  if (badges.includes("blur")) parts.push("blur(2.5px)");
  if (badges.includes("downscale")) parts.push("blur(1px) contrast(0.9)");
  if (badges.includes("cvd")) parts.push("saturate(0.4) sepia(0.25)");
  if (badges.includes("small_viewport")) parts.push("contrast(1.05)");
  return parts.length ? parts.join(" ") : undefined;
}
