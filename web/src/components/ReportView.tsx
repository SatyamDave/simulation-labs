import { useState } from "react";
import { motion } from "framer-motion";
import type { PersonaResult, RunReport, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { API_BASE, artifactUrl } from "../api";
import { OUTCOME_TEXT_CLASS } from "../theme";
import { SurvivalCurve } from "./SurvivalCurve";
import { Heatmap } from "./Heatmap";
import { InsightsPanel } from "./InsightsPanel";

interface Props {
  report: RunReport;
  coordSpace?: Viewport;
  // Live runs pull the real target screenshot for the heatmap backdrop.
  // The offline demo leaves this false so it renders from bundled fixtures.
  live?: boolean;
  onBack?: () => void;
}

// Agent-readiness: can a computer-use agent complete this flow at all? Derived
// client-side from the "ai-agent" persona's outcome (or any persona whose id or
// name mentions "agent"). PASS iff that persona completed the task.
interface AgentVerdict {
  status: "pass" | "fail";
  name: string;
  outcome: RunReport["survival"][number]["outcome"];
  steps: number;
}

function computeAgentVerdict(report: RunReport): AgentVerdict | null {
  const s =
    report.survival.find((p) => p.persona_id === "ai-agent") ??
    report.survival.find(
      (p) =>
        /agent/i.test(p.persona_id) || /agent/i.test(p.persona_name ?? "")
    );
  if (!s) return null;
  const pass = s.completed || s.outcome === "success";
  return {
    status: pass ? "pass" : "fail",
    name: s.persona_name || s.persona_id,
    outcome: s.outcome,
    steps: s.steps_survived,
  };
}

function SectionHeading({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      {sub && <p className="text-sm text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

export function ReportView({ report, coordSpace, live, onBack }: Props) {
  const pct = Math.round((report.completion_rate ?? 0) * 100);
  const counted = report.survival.filter((s) => s.outcome !== "error");
  const survived = counted.filter((s) => s.completed).length;
  const total = counted.length;

  const verdict = computeAgentVerdict(report);
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
      {onBack && (
        <button
          type="button"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors mb-10"
          onClick={onBack}
        >
          ← Back to the grid
        </button>
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

      {verdict && (
        <div className="border-t border-border mt-10 pt-6 flex items-baseline gap-2.5">
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 translate-y-[-1px] ${
              verdict.status === "pass" ? "bg-ok" : "bg-fail"
            }`}
            aria-hidden="true"
          />
          <p className="text-sm leading-relaxed">
            {verdict.status === "pass" ? (
              <>
                An AI agent can complete this flow —{" "}
                <span className="font-medium">{verdict.name}</span> finished in{" "}
                <span className="tabular-nums">{verdict.steps}</span> steps
                with no perturbation.
              </>
            ) : (
              <>
                An AI agent cannot complete this flow —{" "}
                <span className="font-medium">{verdict.name}</span> ran
                unimpaired and still failed (
                {OUTCOME_LABELS[verdict.outcome].toLowerCase()}) after{" "}
                <span className="tabular-nums">{verdict.steps}</span> steps.
              </>
            )}
          </p>
        </div>
      )}

      <section className="border-t border-border mt-10 pt-10">
        <SectionHeading
          title="Survival"
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
            />
          ))}
          {results.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No per-persona receipts in this report.
            </p>
          )}
        </div>
      </section>

      <section className="border-t border-border mt-12 pt-10">
        <SectionHeading
          title="Cross-run insights"
          sub="What the swarm has learned across every site and run — which UX patterns block which impaired users."
        />
        <InsightsPanel />
      </section>
    </motion.div>
  );
}

function ResultCard({
  result,
  name,
}: {
  result: PersonaResult;
  name: string;
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
      </div>
    </article>
  );
}
