// Simulation Labs functional palette + perturbation labels.
// Per web/DESIGN_SYSTEM.md (v3 — Quiet workspace) every color is a state and
// stays quiet — text, small dots, hairlines only: orange = running/live,
// green = survived, red = died/abandoned, neutral = infra error (excluded
// from survival stats, must not read as a human abandon).

import type { PersonaConfig, PersonaOutcome, PerturbationKind } from "./types";

// Literal hex values for the few places that need to compose alpha suffixes
// inline: heatmap radial gradients over screenshots.
export const SUCCESS_HEX = "#448361";
export const FAIL_HEX = "#D44C47";
export const NEUTRAL_HEX = "#787774";

// Outcome -> chart color. CSS variables so charts stay AA in both themes
// (light mode darkens the functional hues). success is the only "good"
// outcome; every non-error outcome is a genuine abandonment; error is infra.
export const OUTCOME_COLOR: Record<PersonaOutcome, string> = {
  success: "var(--ok)",
  step_budget: "var(--fail)",
  time_budget: "var(--fail)",
  stuck: "var(--fail)",
  error: "var(--idle)",
};

// The same mapping as Tailwind utility classes, for markup-level styling.
export const OUTCOME_TEXT_CLASS: Record<PersonaOutcome, string> = {
  success: "text-ok",
  step_budget: "text-fail",
  time_budget: "text-fail",
  stuck: "text-fail",
  error: "text-muted-foreground",
};

// Color-stepped 0-100 score (functional tokens — state, not identity).
// Shared by the report hero, the compare view, and the run index.
export function scoreColor(score: number): string {
  return score >= 70 ? "var(--ok)" : score >= 40 ? "var(--live)" : "var(--fail)";
}

// Chart series colors for the stepped survival curves (quiet, theme-safe):
// the current run draws in text color, a comparison baseline recedes to gray.
export const SERIES_CURRENT = "var(--foreground)";
export const SERIES_BASELINE = "var(--idle)";

// ---------------------------------------------------------------------------
// Perturbation labels — the "which channels are degraded" chips on a tile.
// Tiny lowercase mono structural labels (spec: labels — no icons, no emoji).
// Prefer the persona's declared active_perturbations; if
// absent (sparse fixtures only carry id/name/blurb), infer from the numeric
// fields, then fall back to id keywords so the offline demo still shows
// meaningful labels.
// ---------------------------------------------------------------------------
export interface Badge {
  kind: PerturbationKind;
  text: string; // rendered as-is — keep lowercase
  title: string;
}

const BADGE_META: Record<PerturbationKind, { text: string; title: string }> = {
  blur: { text: "blur", title: "Low vision (blur)" },
  downscale: { text: "downscale", title: "Low acuity" },
  cvd: { text: "cvd", title: "Color-vision deficiency" },
  tremor: { text: "tremor", title: "Hand tremor" },
  small_viewport: { text: "viewport", title: "Small viewport" },
  impatience: { text: "impatient", title: "Impatient" },
  low_literacy: { text: "literal", title: "Low digital literacy" },
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

  return [...kinds].map((k) => {
    // Small viewport reads best as the actual dims (e.g. "390x844").
    if (k === "small_viewport" && p.viewport) {
      return {
        kind: k,
        text: `${p.viewport.width}x${p.viewport.height}`,
        title: BADGE_META[k].title,
      };
    }
    return { kind: k, ...BADGE_META[k] };
  });
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
