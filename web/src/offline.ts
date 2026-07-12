// Offline demo data. The guaranteed-safe hackathon fallback: no backend.
//
// We load the two committed fixtures from /public/fixtures:
//   • events.jsonl  — the canonical run_started (6 personas) + the key beats
//                     (grandma freezes red at 300,145).
//   • run.json      — the full RunReport for the report view.
//
// The raw events.jsonl is deliberately sparse (only a couple of personas step).
// To make the LIVE GRID convincing on a projector, we ENRICH it into a full
// timeline derived from run.json's survival/results — every persona animates,
// then finishes with its true recorded outcome. The load-bearing beat is
// preserved verbatim: grandma-72 abandons at (300,145).

import type {
  PersonaConfig,
  RunEvent,
  RunReport,
  RunStarted,
  StepEvent,
  PersonaStarted,
  PersonaFinished,
  RunFinished,
} from "./types";

const BASE = import.meta.env.BASE_URL || "/";

async function fetchText(path: string): Promise<string> {
  const res = await fetch(`${BASE}fixtures/${path}`);
  if (!res.ok) throw new Error(`offline fixture ${path}: ${res.status}`);
  return res.text();
}

function parseJsonl(text: string): RunEvent[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => JSON.parse(l) as RunEvent);
}

export interface OfflineDemoData {
  timeline: RunEvent[];
  report: RunReport;
}

// Believable in-run captions per persona archetype (keyed loosely by id).
const CAPTIONS: Record<string, string[]> = {
  "grandma-72": [
    "Accepting the cookie wall",
    "Typing her email address",
    "Clicking the big blue 'Explore plans'",
    "Clicking 'Explore plans' again…",
    "Clicking it a third time — nothing happens",
  ],
  "low-vision": [
    "Accepting cookies",
    "Squinting at the grey legal text",
    "Hunting for the sign-up link",
    "Can't find where to start",
  ],
  tremor: [
    "Reaching for the checkbox…",
    "Missed the target — hand tremor",
    "Fat-fingered the wrong link",
    "Missed the email field",
    "Trying the submit button",
    "Slipped off the button again",
    "Retrying the tiny target",
    "Out of tries",
  ],
  "impatient-mobile": [
    "Tapping through the cookie wall",
    "Scrolling fast to find the form",
    "This is taking too long…",
    "Pinch-zooming the tiny text",
    "Bounced — gave up on mobile",
  ],
  "power-user": [
    "Dismissing cookies",
    "Filling the email field",
    "Setting a password",
    "Scrolling to the promo field",
    "Entering the promo code",
    "Finding the grey submit button",
    "Account created ✓",
  ],
  "ai-agent": [
    "Parsing the DOM",
    "Locating the sign-up form",
    "Filling email + password",
    "Resolving the promo field",
    "Submitting the form",
    "Task complete ✓",
  ],
};

const GENERIC_CAPTIONS = [
  "Reading the page",
  "Looking for the form",
  "Filling a field",
  "Scrolling down",
  "Trying a button",
];

function personaTarget(report: RunReport, id: string): [number, number] {
  const res = report.results.find((r) => r.persona_id === id);
  if (res?.failure_coords) return res.failure_coords;
  const hp = report.heatmap_points.find((p) => p.persona_id === id);
  if (hp) return [hp.x, hp.y];
  return [320, 240];
}

// Build per-persona step events that drift toward the persona's death/target
// pixel, capped so the whole replay stays snappy on stage.
function buildSteps(
  runId: string,
  persona: PersonaConfig,
  report: RunReport,
  animate: number
): StepEvent[] {
  const caps = CAPTIONS[persona.id] ?? GENERIC_CAPTIONS;
  const [tx, ty] = personaTarget(report, persona.id);
  const sx = 158;
  const sy = 372; // everyone starts near the cookie banner
  const isTremor = /tremor/.test(persona.id);
  const steps: StepEvent[] = [];
  for (let i = 0; i < animate; i++) {
    const t = animate <= 1 ? 1 : i / (animate - 1);
    let x = Math.round(sx + (tx - sx) * t);
    let y = Math.round(sy + (ty - sy) * t);
    if (isTremor) {
      x += Math.round((Math.random() - 0.5) * 60);
      y += Math.round((Math.random() - 0.5) * 60);
    }
    steps.push({
      event: "step",
      run_id: runId,
      persona_id: persona.id,
      step: i,
      caption: caps[Math.min(i, caps.length - 1)],
      thumbnail_b64: "",
      x,
      y,
    });
  }
  return steps;
}

// Assemble the enriched, interleaved timeline.
export function buildTimeline(
  runStarted: RunStarted,
  report: RunReport
): RunEvent[] {
  const runId = runStarted.run_id;
  const personas = runStarted.personas;
  const timeline: RunEvent[] = [runStarted];

  // Stagger the launches.
  for (const p of personas) {
    const ps: PersonaStarted = {
      event: "persona_started",
      run_id: runId,
      persona_id: p.id,
    };
    timeline.push(ps);
  }

  // Per-persona step lists (capped at 8 for pace; the reported steps_survived
  // still uses the true number from the report).
  const perPersonaSteps: Record<string, StepEvent[]> = {};
  let maxLen = 0;
  for (const p of personas) {
    const sp = report.survival.find((s) => s.persona_id === p.id);
    const survived = sp?.steps_survived ?? 4;
    const animate = Math.max(2, Math.min(8, survived));
    perPersonaSteps[p.id] = buildSteps(runId, p, report, animate);
    maxLen = Math.max(maxLen, perPersonaSteps[p.id].length);
  }

  // Round-robin interleave so tiles animate in parallel.
  for (let i = 0; i < maxLen; i++) {
    for (const p of personas) {
      const s = perPersonaSteps[p.id][i];
      if (s) timeline.push(s);
    }
  }

  // Finishes, in a dramatic order: deaths first (so red blooms across the grid),
  // survivors last.
  const finishes: PersonaFinished[] = [];
  const ordered = [...report.survival].sort((a, b) => {
    if (a.completed !== b.completed) return a.completed ? 1 : -1;
    return a.steps_survived - b.steps_survived;
  });
  for (const s of ordered) {
    const res = report.results.find((r) => r.persona_id === s.persona_id);
    finishes.push({
      event: "persona_finished",
      run_id: runId,
      persona_id: s.persona_id,
      outcome: s.outcome,
      failure_coords: res?.failure_coords ?? null,
      failure_reason:
        res?.failure_reason || (s.completed ? "" : "Abandoned the task"),
      steps_survived: s.steps_survived,
    });
  }
  timeline.push(...finishes);

  const runFinished: RunFinished = {
    event: "run_finished",
    run_id: runId,
    report_url: `/runs/${runId}/report`,
    completion_rate: report.completion_rate,
  };
  timeline.push(runFinished);

  return timeline;
}

export async function loadOfflineDemo(): Promise<OfflineDemoData> {
  const [eventsText, reportText] = await Promise.all([
    fetchText("events.jsonl"),
    fetchText("run.json"),
  ]);
  const rawEvents = parseJsonl(eventsText);
  const report = JSON.parse(reportText) as RunReport;

  const runStarted = rawEvents.find(
    (e): e is RunStarted => e.event === "run_started"
  );
  if (!runStarted) {
    throw new Error("offline: events.jsonl has no run_started event");
  }

  const timeline = buildTimeline(runStarted, report);
  return { timeline, report };
}
