// Client-side run simulator. Produces the exact same RunEvent stream + RunReport
// the real FastAPI backend would emit, so the whole product flow (launch → live
// grid → survival/heatmap report → voice exit-interviews) runs with NO backend and
// NO API keys — reliable for a screen-recorded demo. When VITE_API_BASE is set the
// app talks to the real server instead (see App.tsx); this path is the fallback.
//
// Everything is derived from the operator's real inputs: the target URL selects the
// page backdrop, the task is echoed through the UI, and the chosen personas fail (or
// survive) differentially at exact pixels in a fixed 1280x800 coordinate space.

import type {
  PersonaConfig,
  PersonaOutcome,
  PersonaResult,
  RunEvent,
  RunReport,
  RunStarted,
  StepEvent,
  SurvivalPoint,
  Viewport,
  HeatPoint,
} from "../types";
import { PERSONA_CATALOG } from "../personaCatalog";
import type { LaunchValues } from "../components/LaunchForm";

// The synthetic viewport every persona (and every coordinate) lives in.
export const TARGET_SPACE: Viewport = { width: 1280, height: 800 };

const BASE = import.meta.env.BASE_URL || "/";
const ORIGIN = typeof window !== "undefined" ? window.location.origin : "";

function asset(path: string): string {
  return `${ORIGIN}${BASE}${path}`;
}

// URL → realistic page backdrop (SVG "screenshot" shipped in /public/fixtures/pages).
export function targetBackdrop(url: string): string {
  const u = url.toLowerCase();
  if (/github/.test(u)) return asset("fixtures/pages/github-signup.svg");
  if (/stripe/.test(u)) return asset("fixtures/pages/stripe-register.svg");
  return asset("fixtures/pages/quantumleap.svg");
}

function audioFor(id: string): string {
  return asset(`fixtures/audio/${id}.wav`);
}

// ---------------------------------------------------------------------------
// Per-persona behavioural plan. Coordinates are in TARGET_SPACE (1280x800) and
// land on real elements of the QuantumLeap signup page mock: the blue decoy
// "Explore plans" (~548,543), the recessed grey "Create account" (~726,543), the
// email field (~640,250), and the tiny grey legal block (~620,415).
// ---------------------------------------------------------------------------
interface Plan {
  outcome: PersonaOutcome;
  steps: number; // reported steps_survived
  animate: number; // number of step events streamed to the tile
  death: [number, number] | null; // abandonment pixel (null on success)
  duration_s: number;
  reason: string;
  transcript: string;
  captions: string[];
}

const START: [number, number] = [640, 470];
const SUCCESS_TARGET: [number, number] = [726, 543];

const PLANS: Record<string, Plan> = {
  "power-user": {
    outcome: "success",
    steps: 7,
    animate: 7,
    death: null,
    duration_s: 19.4,
    reason: "",
    transcript:
      "Straightforward enough, once I scrolled down to find the promo field. The grey submit button was odd, but I found it.",
    captions: [
      "Dismissing the cookie banner",
      "Filling in the email field",
      "Setting a 12-character password",
      "Scrolling down to the fine print",
      "Revealing the hidden promo field",
      "Finding the greyed-out submit",
      "Account created ✓",
    ],
  },
  "ai-agent": {
    outcome: "success",
    steps: 6,
    animate: 6,
    death: null,
    duration_s: 8.7,
    reason: "",
    transcript:
      "Located the form, filled the required fields, resolved the hidden promo input, and submitted. Task complete.",
    captions: [
      "Parsing the DOM tree",
      "Locating the sign-up form",
      "Filling email + password",
      "Resolving the hidden promo input",
      "Submitting the form",
      "Task complete ✓",
    ],
  },
  "grandma-72": {
    outcome: "stuck",
    steps: 4,
    animate: 5,
    death: [548, 543],
    duration_s: 44.1,
    reason:
      "Clicked the blue 'Explore plans' decoy three times expecting it to create the account — never noticed the recessed grey 'Create account'.",
    transcript:
      "I kept pressing the big blue button, because that is usually the one you press. But it just kept talking about plans. I never did find where to actually make my account.",
    captions: [
      "Accepting the cookie wall",
      "Typing her email address",
      "Clicking the big blue 'Explore plans'",
      "Clicking 'Explore plans' again…",
      "Pressing it a third time — nothing happens",
    ],
  },
  "low-vision": {
    outcome: "stuck",
    steps: 3,
    animate: 5,
    death: [640, 420],
    duration_s: 33.5,
    reason:
      "The 10px #b8b8b8 legal text and the washed-out submit button were illegible — could not distinguish the primary action.",
    transcript:
      "The words I needed were tiny and grey, the same colour as the background. I could not tell the buttons apart, so I gave up looking.",
    captions: [
      "Accepting cookies",
      "Squinting at the grey 10px legal text",
      "Can't tell the two buttons apart",
      "Wandering the page for a sign-up link",
      "Gives up — nothing is legible",
    ],
  },
  colorblind: {
    outcome: "stuck",
    steps: 9,
    animate: 6,
    death: [726, 543],
    duration_s: 51.2,
    reason:
      "Submitted three times; the only validation cue was a red input border. With deuteranopia the error was invisible, so the same submit looked like it did nothing.",
    transcript:
      "I filled everything in and pressed create account, but nothing happened. There was no message telling me what was wrong. I tried three times, then I left.",
    captions: [
      "Dismissing cookies",
      "Filling email + password",
      "Pressing 'Create account'",
      "No visible error — trying again",
      "Third submit, still no feedback",
      "Abandons — never saw the red border",
    ],
  },
  tremor: {
    outcome: "step_budget",
    steps: 12,
    animate: 8,
    death: [640, 250],
    duration_s: 62.0,
    reason:
      "±14px coordinate noise put every click off-target; the small inputs and buttons were smaller than the tremor, so it burned its whole step budget missing.",
    transcript:
      "Every time I aimed for the little box, my hand slipped and I hit the wrong thing. The targets were just too small for me to hit.",
    captions: [
      "Reaching for the cookie button…",
      "Missed — hit the header instead",
      "Aiming at the email field",
      "Slipped off the input again",
      "Fat-fingered the password box",
      "Missed the tiny submit target",
      "Retrying the small control",
      "Out of tries — step budget spent",
    ],
  },
  "non-native": {
    outcome: "stuck",
    steps: 6,
    animate: 6,
    death: [615, 415],
    duration_s: 39.8,
    reason:
      "Idiomatic legal jargon ('Data Processing Addendum', 'Acceptable Use Policy') was unparseable — would not agree to terms he could not read.",
    transcript:
      "There were words I did not understand. Data processing addendum. Acceptable use. I was not sure what I was agreeing to, so I stopped.",
    captions: [
      "Accepting cookies",
      "Reading 'Data Processing Addendum'…",
      "Unsure what 'Acceptable Use' means",
      "Re-reading the dense legal text",
      "Hesitating over the terms",
      "Stops — won't agree to unclear terms",
    ],
  },
  "impatient-mobile": {
    outcome: "time_budget",
    steps: 5,
    animate: 5,
    death: [560, 330],
    duration_s: 12.3,
    reason:
      "On a 390px viewport the required promo field only appears after scrolling; patience ran out (45s deadline) before the form was even complete.",
    transcript:
      "It was taking forever, and the form kept asking for more. I did not have time for a promo code I never received. I bounced.",
    captions: [
      "Tapping through the cookie wall",
      "Scrolling fast for the form",
      "This is taking too long…",
      "Pinch-zooming the tiny text",
      "Bounced — gave up on mobile",
    ],
  },
};

const GENERIC_PLAN: Plan = {
  outcome: "stuck",
  steps: 4,
  animate: 5,
  death: [640, 400],
  duration_s: 30.0,
  reason: "Abandoned the task before reaching the goal.",
  transcript: "I couldn't work out how to finish, so I gave up.",
  captions: [
    "Reading the page",
    "Looking for the form",
    "Filling a field",
    "Trying a button",
    "Gives up",
  ],
};

function planFor(id: string): Plan {
  return PLANS[id] ?? GENERIC_PLAN;
}

// Deterministic small pseudo-noise (no Math.random — keeps replays stable).
function wobble(seed: number, mag: number): number {
  const s = Math.sin(seed * 12.9898) * 43758.5453;
  return (s - Math.floor(s) - 0.5) * 2 * mag;
}

function buildSteps(
  runId: string,
  persona: PersonaConfig,
  plan: Plan
): StepEvent[] {
  const target = plan.death ?? SUCCESS_TARGET;
  const isTremor = persona.id === "tremor";
  const n = plan.animate;
  const out: StepEvent[] = [];
  for (let i = 0; i < n; i++) {
    const t = n <= 1 ? 1 : i / (n - 1);
    let x = Math.round(START[0] + (target[0] - START[0]) * t);
    let y = Math.round(START[1] + (target[1] - START[1]) * t);
    const mag = isTremor ? 46 : 10;
    x += Math.round(wobble(i * 7.1 + persona.id.length, mag));
    y += Math.round(wobble(i * 3.3 + persona.id.length * 2, mag));
    out.push({
      event: "step",
      run_id: runId,
      persona_id: persona.id,
      step: i,
      caption: plan.captions[Math.min(i, plan.captions.length - 1)],
      thumbnail_b64: "",
      x,
      y,
    });
  }
  return out;
}

export interface SimulatedRun {
  timeline: RunEvent[];
  report: RunReport;
  backdrop: string;
  coordSpace: Viewport;
}

export function simulateRun(values: LaunchValues): SimulatedRun {
  const runId = `sim-${values.persona_ids.length}-${values.target_url.length}`;
  const backdrop = targetBackdrop(values.target_url);

  // Resolve selected personas (in catalog order for a stable, pleasing grid).
  const chosen = PERSONA_CATALOG.filter((p) =>
    values.persona_ids.includes(p.id)
  );
  const personas: PersonaConfig[] = chosen.map((p) => ({ ...p }));

  const runStarted: RunStarted = {
    event: "run_started",
    run_id: runId,
    target_url: values.target_url,
    task: values.task,
    personas,
  };

  const timeline: RunEvent[] = [runStarted];
  for (const p of personas) {
    timeline.push({
      event: "persona_started",
      run_id: runId,
      persona_id: p.id,
    });
  }

  // Per-persona step lists, round-robin interleaved so tiles animate in parallel.
  const perPersona: Record<string, StepEvent[]> = {};
  let maxLen = 0;
  for (const p of personas) {
    perPersona[p.id] = buildSteps(runId, p, planFor(p.id));
    maxLen = Math.max(maxLen, perPersona[p.id].length);
  }
  for (let i = 0; i < maxLen; i++) {
    for (const p of personas) {
      const s = perPersona[p.id][i];
      if (s) timeline.push(s);
    }
  }

  // Report pieces.
  const survival: SurvivalPoint[] = [];
  const results: PersonaResult[] = [];
  const heatmap_points: HeatPoint[] = [];
  let successes = 0;
  let counted = 0;

  for (const p of personas) {
    const plan = planFor(p.id);
    const completed = plan.outcome === "success";
    if (plan.outcome !== "error") counted++;
    if (completed) successes++;

    survival.push({
      persona_id: p.id,
      persona_name: p.name,
      outcome: plan.outcome,
      steps_survived: plan.steps,
      completed,
    });

    results.push({
      persona_id: p.id,
      outcome: plan.outcome,
      steps: [],
      failure_coords: plan.death,
      failure_step: completed ? null : plan.steps,
      failure_reason: plan.reason,
      duration_s: plan.duration_s,
      video_path: null,
      transcript: plan.transcript,
      audio_path: audioFor(p.id),
    });

    if (!completed && plan.death) {
      heatmap_points.push({
        x: plan.death[0],
        y: plan.death[1],
        weight: 1,
        persona_id: p.id,
      });
    }
  }

  const completion_rate = counted ? successes / counted : 0;

  // Finishes: deaths first (red blooms across the grid), survivors last.
  const ordered = [...survival].sort((a, b) => {
    if (a.completed !== b.completed) return a.completed ? 1 : -1;
    return a.steps_survived - b.steps_survived;
  });
  for (const s of ordered) {
    const plan = planFor(s.persona_id);
    timeline.push({
      event: "persona_finished",
      run_id: runId,
      persona_id: s.persona_id,
      outcome: s.outcome,
      failure_coords: plan.death,
      failure_reason: plan.reason || (s.completed ? "" : "Abandoned the task"),
      steps_survived: s.steps_survived,
    });
  }

  timeline.push({
    event: "run_finished",
    run_id: runId,
    report_url: `/runs/${runId}/report`,
    completion_rate,
  });

  const report: RunReport = {
    run_id: runId,
    target_url: values.target_url,
    task: values.task,
    contract_version: "1.0.0",
    results,
    survival,
    heatmap_points,
    completion_rate,
    generated_at: "2026-07-12T00:00:00Z",
  };

  return { timeline, report, backdrop, coordSpace: TARGET_SPACE };
}
