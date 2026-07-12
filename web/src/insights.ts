// Run insights: composite score + accessibility-evidence mapping.
//
// TypeScript mirror of the frozen wire format documented in
// src/ghostpanel/report/insights.py — the server writes it to
// artifacts/<run_id>/insights.json after a run. `fetchInsights` pulls that
// file; `computeFallbackInsights` recreates a best-effort equivalent purely
// from the RunReport so the offline demo (and older runs without the file)
// still render the insights panel.

import type {
  PersonaConfig,
  PersonaOutcome,
  PersonaResult,
  PerturbationKind,
  RunReport,
  StepRecord,
  SurvivalPoint,
} from "./types";
import { OUTCOME_LABELS } from "./types";
import { artifactUrl } from "./api";
import { PERSONA_CATALOG } from "./personaCatalog";
import { perturbationBadges } from "./theme";

// ---------------------------------------------------------------------------
// Wire types (frozen — mirror insights.py, contracts.py wins on drift)
// ---------------------------------------------------------------------------
export interface AgentReadiness {
  score: number; // 0-100
  outcome: PersonaOutcome;
  steps: number;
  note: string;
}

export interface WcagFinding {
  persona_id: string;
  persona_name: string;
  criterion: string; // e.g. "1.4.3"
  name: string; // e.g. "Contrast (Minimum)"
  level: string; // "A" | "AA" | "AAA"
  standard_ref: string; // EN 301 549 clause, e.g. "9.1.4.3"
  evidence: string; // grounded in the action trace / failure pixel
  failure_step: number | null;
}

// --- additive stats keys (newer servers write these; treat all as optional) --
export interface RunMeta {
  run_id: string;
  target_url: string;
  task: string;
  generated_at: string;
  personas: number;
}

export interface RunLevelStats {
  total_steps: number;
  total_duration_s: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  actions_by_type: Record<string, number>; // ActionType value -> count
  blocked_actions: number; // steps blocked by the policy gateway
  personas_succeeded: number;
  personas_abandoned: number;
  personas_errored: number;
  median_steps_to_abandon: number | null;
  fastest_success_steps: number | null;
}

export interface PersonaStats {
  persona_id: string;
  persona_name: string;
  outcome: PersonaOutcome;
  steps: number;
  steps_survived: number;
  duration_s: number;
  avg_latency_ms: number;
  actions_by_type: Record<string, number>;
  blocked_actions: number;
  max_repeated_action: number; // longest run of identical actions ("rage clicks")
  perturbations: PerturbationKind[];
}

export interface RunStats {
  run: RunLevelStats;
  personas: PersonaStats[];
}

export interface SurvivalSeriesPoint {
  step: number;
  alive: number;
}

export interface RunInsights {
  ghostpanel_score: number; // 0-100 composite survival score
  agent_readiness: AgentReadiness | null;
  wcag_findings: WcagFinding[];
  summary: string;
  // Additive keys — possibly absent on older servers / offline fallback fills.
  meta?: RunMeta;
  stats?: RunStats;
  survival_series?: SurvivalSeriesPoint[];
}

// GET artifacts/<run_id>/insights.json — null on 404 / network failure so the
// caller can fall back to the client-side computation.
export async function fetchInsights(
  runId: string
): Promise<RunInsights | null> {
  const url = artifactUrl(`artifacts/${runId}/insights.json`);
  if (!url) return null;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return (await res.json()) as RunInsights;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Client-side fallback (offline replay / runs without insights.json)
// ---------------------------------------------------------------------------

// Perturbation kind -> the WCAG 2.2 success criterion it most directly
// evidences, with the matching EN 301 549 clause (Table 9.x mirrors the
// criterion numbering for A/AA).
const WCAG_BY_PERTURBATION: Partial<
  Record<PerturbationKind, Pick<WcagFinding, "criterion" | "name" | "level" | "standard_ref">>
> = {
  blur: {
    criterion: "1.4.3",
    name: "Contrast (Minimum)",
    level: "AA",
    standard_ref: "9.1.4.3",
  },
  downscale: {
    criterion: "1.4.3",
    name: "Contrast (Minimum)",
    level: "AA",
    standard_ref: "9.1.4.3",
  },
  cvd: {
    criterion: "1.4.1",
    name: "Use of Color",
    level: "A",
    standard_ref: "9.1.4.1",
  },
  tremor: {
    criterion: "2.5.8",
    name: "Target Size (Minimum)",
    level: "AA",
    standard_ref: "9.2.5.8",
  },
  impatience: {
    criterion: "2.2.1",
    name: "Timing Adjustable",
    level: "A",
    standard_ref: "9.2.2.1",
  },
  small_viewport: {
    criterion: "1.4.10",
    name: "Reflow",
    level: "AA",
    standard_ref: "9.1.4.10",
  },
  // low_literacy is resolved per persona in wcagRuleFor(): a non-native
  // reader evidences Reading Level (AAA — outside EN 301 549's A/AA scope,
  // hence no clause); low digital literacy evidences Headings and Labels.
};

function wcagRuleFor(
  kind: PerturbationKind,
  persona: PersonaConfig
): Pick<WcagFinding, "criterion" | "name" | "level" | "standard_ref"> | null {
  if (kind === "low_literacy") {
    const nonNative =
      (persona.language && !persona.language.startsWith("en")) ||
      /non-native|esl/i.test(`${persona.id} ${persona.name}`);
    return nonNative
      ? { criterion: "3.1.5", name: "Reading Level", level: "AAA", standard_ref: "—" }
      : { criterion: "2.4.6", name: "Headings and Labels", level: "AA", standard_ref: "9.2.4.6" };
  }
  return WCAG_BY_PERTURBATION[kind] ?? null;
}

// The catalog knows each persona's perturbations; unknown ids fall through to
// perturbationBadges' keyword inference so we never return blank findings for
// a named impairment persona.
function personaConfigFor(s: SurvivalPoint): PersonaConfig {
  return (
    PERSONA_CATALOG.find((c) => c.id === s.persona_id) ?? {
      id: s.persona_id,
      name: s.persona_name || s.persona_id,
    }
  );
}

function evidenceFor(
  s: SurvivalPoint,
  res: PersonaResult | undefined,
  label: string
): string {
  if (res?.failure_reason) {
    return `${label} — “${res.failure_reason}”`;
  }
  return `Abandoned (${OUTCOME_LABELS[s.outcome].toLowerCase()}) after ${
    s.steps_survived
  } steps under the “${label}” perturbation.`;
}

// Agent readiness derived from the "ai-agent" persona (or any persona whose
// id/name mentions "agent"). PASS iff that persona completed the task.
function deriveAgentReadiness(report: RunReport): AgentReadiness | null {
  const s =
    report.survival.find((p) => p.persona_id === "ai-agent") ??
    report.survival.find(
      (p) => /agent/i.test(p.persona_id) || /agent/i.test(p.persona_name ?? "")
    );
  if (!s || s.outcome === "error") return null; // infra failure ≠ verdict
  const pass = s.completed || s.outcome === "success";
  const name = s.persona_name || s.persona_id;
  return {
    score: pass ? 100 : 0,
    outcome: s.outcome,
    steps: s.steps_survived,
    note: pass
      ? `${name} completed the task in ${s.steps_survived} steps with no perturbation — this flow is ready for computer-use agents.`
      : `${name} ran unimpaired and still failed (${OUTCOME_LABELS[
          s.outcome
        ].toLowerCase()}) after ${s.steps_survived} steps — this flow is not yet agent-ready.`,
  };
}

// ---------------------------------------------------------------------------
// Client-side stats (meta / stats / survival_series) from the RunReport alone,
// mirroring the server's insights.py wire shape — the offline demo and older
// servers get the full stats dashboard from this.
// ---------------------------------------------------------------------------

// Note stamped on a StepRecord when the policy gateway blocked the action.
export const POLICY_BLOCKED_NOTE = "policy_blocked";

function isBlockedStep(s: StepRecord): boolean {
  return (
    s.note === POLICY_BLOCKED_NOTE ||
    (s.action?.caption ?? "").startsWith("🛡")
  );
}

// Longest run of identical consecutive actions — the "rage click" count.
function maxRepeatedAction(steps: StepRecord[]): number {
  let best = 0;
  let cur = 0;
  let prev: string | null = null;
  for (const s of steps) {
    const key =
      s.action?.caption || s.action?.raw || s.action?.type || "";
    cur = key && key === prev ? cur + 1 : 1;
    prev = key || null;
    if (cur > best) best = cur;
  }
  return best;
}

// Nearest-rank p95 (matches the server's method).
function p95(latencies: number[]): number {
  if (!latencies.length) return 0;
  const sorted = [...latencies].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil(0.95 * sorted.length));
  return sorted[rank - 1];
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]
    : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

function countActions(steps: StepRecord[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const s of steps) {
    const t = s.action?.type;
    if (!t) continue;
    counts[t] = (counts[t] ?? 0) + 1;
  }
  return counts;
}

// meta + stats + survival_series derived purely from the RunReport.
export function computeFallbackStats(
  report: RunReport
): Required<Pick<RunInsights, "meta" | "stats" | "survival_series">> {
  const meta: RunMeta = {
    run_id: report.run_id,
    target_url: report.target_url,
    task: report.task,
    generated_at: report.generated_at ?? "",
    personas: report.survival.length,
  };

  const personas: PersonaStats[] = report.survival.map((s) => {
    const res = report.results.find((r) => r.persona_id === s.persona_id);
    const steps = res?.steps ?? [];
    const latencies = steps
      .map((st) => st.latency_ms ?? 0)
      .filter((ms) => ms > 0);
    const avg = latencies.length
      ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
      : 0;
    return {
      persona_id: s.persona_id,
      persona_name: s.persona_name || s.persona_id,
      outcome: s.outcome,
      steps: Math.max(steps.length, s.steps_survived),
      steps_survived: s.steps_survived,
      duration_s: res?.duration_s ?? 0,
      avg_latency_ms: avg,
      actions_by_type: countActions(steps),
      blocked_actions: steps.filter(isBlockedStep).length,
      max_repeated_action: maxRepeatedAction(steps),
      perturbations: perturbationBadges(personaConfigFor(s)).map(
        (b) => b.kind
      ),
    };
  });

  const counted = report.survival.filter((s) => s.outcome !== "error");
  const succeeded = counted.filter(
    (s) => s.completed || s.outcome === "success"
  );
  const abandoned = counted.filter(
    (s) => !(s.completed || s.outcome === "success")
  );

  const allLatencies = report.results.flatMap((r) =>
    (r.steps ?? []).map((st) => st.latency_ms ?? 0).filter((ms) => ms > 0)
  );
  const actionsByType: Record<string, number> = {};
  for (const p of personas) {
    for (const [t, n] of Object.entries(p.actions_by_type)) {
      actionsByType[t] = (actionsByType[t] ?? 0) + n;
    }
  }

  const run: RunLevelStats = {
    total_steps: personas.reduce((a, p) => a + p.steps_survived, 0),
    total_duration_s:
      Math.round(personas.reduce((a, p) => a + p.duration_s, 0) * 10) / 10,
    avg_latency_ms: allLatencies.length
      ? Math.round(
          allLatencies.reduce((a, b) => a + b, 0) / allLatencies.length
        )
      : 0,
    p95_latency_ms: p95(allLatencies),
    actions_by_type: actionsByType,
    blocked_actions: personas.reduce((a, p) => a + p.blocked_actions, 0),
    personas_succeeded: succeeded.length,
    personas_abandoned: abandoned.length,
    personas_errored: report.survival.length - counted.length,
    median_steps_to_abandon: median(abandoned.map((s) => s.steps_survived)),
    fastest_success_steps: succeeded.length
      ? Math.min(...succeeded.map((s) => s.steps_survived))
      : null,
  };

  // Stepped survival series: personas (non-error) still in the flow at step N.
  const maxStep = counted.length
    ? Math.max(...counted.map((s) => s.steps_survived))
    : 0;
  const survival_series: SurvivalSeriesPoint[] = [];
  for (let step = 0; step <= maxStep; step++) {
    survival_series.push({
      step,
      alive: counted.filter((s) => s.steps_survived >= step).length,
    });
  }

  return { meta, stats: { run, personas }, survival_series };
}

// Fill any missing additive keys (older servers / offline) from the report so
// the stats dashboard always renders. Server-computed values win when present.
export function withDerivedStats(
  insights: RunInsights,
  report: RunReport
): RunInsights {
  if (insights.meta && insights.stats && insights.survival_series?.length) {
    return insights;
  }
  const fb = computeFallbackStats(report);
  return {
    ...insights,
    meta: insights.meta ?? fb.meta,
    stats: insights.stats ?? fb.stats,
    survival_series: insights.survival_series?.length
      ? insights.survival_series
      : fb.survival_series,
  };
}

export function computeFallbackInsights(report: RunReport): RunInsights {
  const counted = report.survival.filter((s) => s.outcome !== "error");
  const successes = counted.filter(
    (s) => s.completed || s.outcome === "success"
  ).length;
  const score = counted.length
    ? Math.round((100 * successes) / counted.length)
    : 0;

  const findings: WcagFinding[] = [];
  for (const s of counted) {
    if (s.completed || s.outcome === "success") continue;
    const persona = personaConfigFor(s);
    const res = report.results.find((r) => r.persona_id === s.persona_id);
    const seen = new Set<string>();
    for (const badge of perturbationBadges(persona)) {
      const rule = wcagRuleFor(badge.kind, persona);
      if (!rule || seen.has(rule.criterion)) continue;
      seen.add(rule.criterion);
      findings.push({
        persona_id: s.persona_id,
        persona_name: s.persona_name || s.persona_id,
        ...rule,
        evidence: evidenceFor(s, res, badge.title),
        failure_step: res?.failure_step ?? null,
      });
    }
  }

  return {
    ghostpanel_score: score,
    agent_readiness: deriveAgentReadiness(report),
    wcag_findings: findings,
    summary: `${successes} of ${counted.length} personas completed the task.`,
    ...computeFallbackStats(report),
  };
}
