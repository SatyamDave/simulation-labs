import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { PersonaResult, RunReport, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { API_BASE, artifactUrl } from "../api";
import { OUTCOME_TEXT_CLASS, scoreColor } from "../theme";
import {
  computeFallbackInsights,
  fetchInsights,
  withDerivedStats,
  type AgentReadiness,
  type RunInsights,
  type WcagFinding,
} from "../insights";
import { AskPersona } from "./AskPersona";
import { SurvivalCurve } from "./SurvivalCurve";
import { Heatmap } from "./Heatmap";
import { StatsPanel } from "./StatsPanel";
import { PolicyPanel } from "./PolicyPanel";

interface Props {
  report: RunReport;
  coordSpace?: Viewport;
  // Live runs pull the real target screenshot for the heatmap backdrop.
  // The offline demo leaves this false so it renders from bundled fixtures.
  live?: boolean;
  onBack?: () => void;
  // Server-backed report screens offer "Compare with another run".
  onCompare?: () => void;
}

function SectionHeading({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      {sub && <p className="text-sm text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

export function ReportView({ report, coordSpace, live, onBack, onCompare }: Props) {
  const pct = Math.round((report.completion_rate ?? 0) * 100);
  const counted = report.survival.filter((s) => s.outcome !== "error");
  const survived = counted.filter((s) => s.completed).length;
  const total = counted.length;

  // Server-written insights.json when the backend is up; a client-side
  // fallback (offline replay / older runs without the file) otherwise.
  const fallbackInsights = useMemo(
    () => computeFallbackInsights(report),
    [report]
  );
  const [serverInsights, setServerInsights] = useState<RunInsights | null>(
    null
  );
  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    fetchInsights(report.run_id).then((ins) => {
      if (!cancelled && ins) setServerInsights(ins);
    });
    return () => {
      cancelled = true;
    };
  }, [live, report.run_id]);
  // Server copy may predate the additive meta/stats/survival_series keys —
  // fill anything missing from the report so the dashboard always renders.
  const insights = withDerivedStats(serverInsights ?? fallbackInsights, report);

  const liveBackdrop = live
    ? `${API_BASE}/artifacts/${report.run_id}/target.png`
    : undefined;

  const nameOf = (id: string) =>
    report.survival.find((s) => s.persona_id === id)?.persona_name || id;

  // Dead first — the receipts that matter.
  const results = [...report.results].sort((a, b) => {
    const aw = a.outcome === "success" ? 1 : 0;
    const bw = b.outcome === "success" ? 1 : 0;
    return aw - bw;
  });

  return (
    <motion.div
      className="mx-auto max-w-3xl"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      {(onBack || onCompare) && (
        <div className="flex items-center gap-6 mb-10">
          {onBack && (
            <button
              type="button"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={onBack}
            >
              ← Back to the grid
            </button>
          )}
          {onCompare && (
            <button
              type="button"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={onCompare}
              title="Before/after: overlay this run against another run on this server"
            >
              compare with another run →
            </button>
          )}
        </div>
      )}

      <header>
        <p
          className={`text-6xl md:text-7xl font-semibold tracking-tight tabular-nums leading-none ${
            pct > 50 ? "text-ok" : "text-fail"
          }`}
        >
          {pct}%
        </p>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight mt-6">
          <span className="tabular-nums">
            {survived} of {total}
          </span>{" "}
          personas completed “{report.task}”
        </h1>
        <p className="text-muted-foreground mt-2">
          <span className="tabular-nums">{total - survived}</span> abandoned
          the flow. Here is exactly where, and why.
        </p>
        <p className="font-mono text-xs text-muted-foreground mt-3 break-all">
          {report.target_url}
        </p>
      </header>

      {live && (
        <div className="mt-8">
          <PolicyPanel />
        </div>
      )}

      {insights.agent_readiness && (
        <AgentReadinessLine agent={insights.agent_readiness} />
      )}

      <section className="border-t border-border mt-10 pt-10">
        <SectionHeading
          title="Simulation score"
          sub="Composite survival score for this flow, 0–100."
        />
        <p className="flex items-baseline gap-3">
          <span
            className="text-5xl font-semibold tracking-tight tabular-nums leading-none"
            style={{ color: scoreColor(insights.ghostpanel_score) }}
          >
            {insights.ghostpanel_score}
            <span className="text-xl text-muted-foreground font-normal">
              /100
            </span>
          </span>
          <span className="text-sm text-muted-foreground">
            {insights.summary}
          </span>
        </p>
        <WcagEvidence findings={insights.wcag_findings} />
      </section>

      <section className="border-t border-border mt-12 pt-10">
        <SectionHeading
          title="Run statistics"
          sub="Effort and friction signals across the whole swarm."
        />
        <StatsPanel insights={insights} />
      </section>

      <section className="border-t border-border mt-12 pt-10">
        <SectionHeading
          title="Per-persona outcome"
          sub="How far each persona got before finishing or giving up."
        />
        <SurvivalCurve survival={report.survival} />
      </section>

      <section className="border-t border-border mt-12 pt-10">
        <SectionHeading
          title="Where they gave up"
          sub="Abandonment points on your actual page."
        />
        <Heatmap
          points={report.heatmap_points}
          liveBackdrop={liveBackdrop}
          coordSpace={coordSpace}
        />
      </section>

      <section className="border-t border-border mt-12 pt-10">
        <SectionHeading
          title="Exit interviews"
          sub="Grounded in each persona's real action trace — video, cloned-voice interview, and the moment they quit."
        />
        <div className="grid sm:grid-cols-2 gap-4">
          {results.map((r) => (
            <ResultCard
              key={r.persona_id}
              result={r}
              name={nameOf(r.persona_id)}
              // The mic/Q&A flow needs the backend — hidden in the offline demo.
              askRunId={live ? report.run_id : undefined}
            />
          ))}
          {results.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No per-persona receipts in this report.
            </p>
          )}
        </div>
      </section>

      <WhyItMatters />
    </motion.div>
  );
}

// One quiet verdict line: can a computer-use agent complete this flow at all?
// Derived by insights.ts from the unimpaired "ai-agent" persona's outcome.
function AgentReadinessLine({ agent }: { agent: AgentReadiness }) {
  const pass = agent.outcome === "success";
  return (
    <div className="border-t border-border mt-10 pt-6 flex items-baseline gap-2.5">
      <span
        className={`w-1.5 h-1.5 rounded-full shrink-0 translate-y-[-1px] ${
          pass ? "bg-ok" : "bg-fail"
        }`}
        aria-hidden="true"
      />
      <p className="text-sm leading-relaxed">
        <span className="font-medium">
          {pass
            ? "An AI agent can complete this flow"
            : "An AI agent cannot complete this flow"}
        </span>{" "}
        — {agent.note ||
          `${OUTCOME_LABELS[agent.outcome].toLowerCase()} after ${
            agent.steps
          } steps.`}{" "}
        <span className="font-mono text-xs text-muted-foreground whitespace-nowrap tabular-nums">
          agent readiness {agent.score}/100
        </span>
      </p>
    </div>
  );
}

function WcagEvidence({ findings }: { findings: WcagFinding[] }) {
  return (
    <div className="mt-8">
      <h3 className="text-sm font-medium">Accessibility evidence</h3>
      <p className="text-xs text-muted-foreground mt-1 mb-3">
        Each row is evidenced by a video receipt and an exact failure pixel —
        WCAG 2.2 / EN 301 549 mapping.
      </p>
      {findings.length === 0 ? (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span
            className="w-1.5 h-1.5 rounded-full bg-ok shrink-0"
            aria-hidden="true"
          />
          No accessibility failures evidenced in this run.
        </p>
      ) : (
        <div className="gp-table-scroll">
          <table className="gp-table">
            <thead>
              <tr>
                <th>persona</th>
                <th>wcag 2.2 criterion</th>
                <th>en 301 549</th>
                <th>evidence</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f, i) => (
                <tr key={`${f.persona_id}-${f.criterion}-${i}`}>
                  <td className="font-medium whitespace-nowrap">
                    {f.persona_name}
                  </td>
                  <td>
                    <span className="font-mono text-xs tabular-nums">
                      {f.criterion}
                    </span>{" "}
                    {f.name}{" "}
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {f.level}
                    </span>
                  </td>
                  <td className="font-mono text-xs text-muted-foreground whitespace-nowrap tabular-nums">
                    {f.standard_ref}
                  </td>
                  <td className="text-muted-foreground">
                    {f.evidence}
                    {f.failure_step != null && (
                      <span className="font-mono text-[10px] whitespace-nowrap tabular-nums">
                        {" "}
                        · step {f.failure_step}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// Report footer, small print: the market context in hard numbers, with the
// source named inline for each claim.
function WhyItMatters() {
  return (
    <details className="border-t border-border mt-12 pt-6 pb-2 group">
      <summary className="text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer list-none">
        Why this matters — the market in four numbers
      </summary>
      <ul className="mt-4 flex flex-col gap-2 text-sm text-muted-foreground leading-relaxed list-disc pl-5">
        <li>
          <span className="font-medium text-foreground">2,019</span> US
          digital-accessibility lawsuits were filed in H1 2025 alone{" "}
          <span className="font-mono text-xs">(UsableNet)</span>.
        </li>
        <li>
          The{" "}
          <span className="font-medium text-foreground">
            EU Accessibility Act
          </span>{" "}
          has been in force since June 2025 — EN&nbsp;301&nbsp;549 conformity
          gives a legal presumption of conformity{" "}
          <span className="font-mono text-xs">(Directive (EU) 2019/882)</span>.
        </li>
        <li>
          Prompt-based LLM personas reproduce real user actions at only{" "}
          <span className="font-medium text-foreground">11.86%</span>{" "}
          <span className="font-mono text-xs">(arXiv 2503.20749)</span> —
          Ghostpanel degrades the perception channel mechanically instead of
          asking a model to roleplay.
        </li>
        <li>
          Cloudflare's Agent Readiness Score scans what sites declare;
          Ghostpanel measures what agents{" "}
          <span className="font-medium text-foreground">survive</span>.
        </li>
      </ul>
    </details>
  );
}

function ResultCard({
  result,
  name,
  askRunId,
}: {
  result: PersonaResult;
  name: string;
  // Set on live (server-backed) reports only: enables the ask-a-question flow.
  askRunId?: string;
}) {
  const [videoOk, setVideoOk] = useState(true);
  const [audioOk, setAudioOk] = useState(true);
  const success = result.outcome === "success";
  const video = artifactUrl(result.video_path);
  const audio = artifactUrl(result.audio_path);

  return (
    <article className="rounded-xl border border-border bg-card flex flex-col overflow-hidden">
      <header className="flex items-center gap-2 px-4 pt-3 pb-2 min-w-0">
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            success ? "bg-ok" : "bg-fail"
          }`}
          aria-hidden="true"
        />
        <span className="text-sm font-medium truncate">{name}</span>
        <span
          className={`ml-auto font-mono text-[11px] whitespace-nowrap tabular-nums ${OUTCOME_TEXT_CLASS[result.outcome]}`}
        >
          {success ? "survived" : "died"}
          {result.failure_step != null && !success && (
            <> · step {result.failure_step}</>
          )}
          {result.duration_s ? <> · {result.duration_s.toFixed(1)}s</> : null}
        </span>
      </header>

      <div className="flex flex-col gap-3 px-4 pb-4">
        {!success && result.failure_reason && (
          <p className="text-xs text-fail/80 leading-relaxed">
            {OUTCOME_LABELS[result.outcome].toLowerCase()} — “
            {result.failure_reason}”
            {result.failure_coords && (
              <span className="font-mono whitespace-nowrap tabular-nums">
                {" "}
                @ {result.failure_coords[0]},{result.failure_coords[1]}
              </span>
            )}
          </p>
        )}

        {video && videoOk ? (
          <video
            className="w-full rounded-lg border border-border bg-surface block aspect-[16/10]"
            controls
            preload="metadata"
            onError={() => setVideoOk(false)}
            src={video}
          />
        ) : (
          <div className="rounded-lg border border-border bg-surface aspect-[16/10] flex items-center justify-center">
            <p className="text-xs text-muted-foreground">
              {video ? "Video needs the backend" : "No video recorded"}
            </p>
          </div>
        )}

        <div>
          <p className="text-xs text-muted-foreground mb-2">
            Exit interview — in {name}'s cloned voice
          </p>
          {audio && audioOk ? (
            <audio
              className="w-full mb-3"
              controls
              preload="none"
              onError={() => setAudioOk(false)}
              src={audio}
            />
          ) : (
            <p className="text-xs text-muted-foreground mb-3">
              {audio ? "Audio needs the backend" : "No audio recorded"}
            </p>
          )}
          {result.transcript ? (
            <blockquote className="border-l-2 border-border pl-3 text-sm leading-relaxed">
              “{result.transcript}”
            </blockquote>
          ) : (
            <p className="border-l-2 border-border pl-3 text-sm text-muted-foreground">
              No transcript recorded.
            </p>
          )}
        </div>

        {askRunId && !success && (
          <AskPersona
            runId={askRunId}
            personaId={result.persona_id}
            name={name}
          />
        )}
      </div>
    </article>
  );
}
