import { useState } from "react";
import { motion } from "framer-motion";
import type { PersonaResult, RunReport, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { API_BASE, artifactUrl } from "../api";
import { OUTCOME_TEXT_CLASS } from "../theme";
import { SurvivalCurve } from "./SurvivalCurve";
import { Heatmap } from "./Heatmap";
import { VitalLine } from "./VitalLine";
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
    <div className="flex flex-col gap-8">
      <motion.header
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-6"
      >
        {onBack && (
          <button
            type="button"
            className="self-start font-mono text-[11px] uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            onClick={onBack}
          >
            ← Back to grid
          </button>
        )}
        <div>
          <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-4">
            Run report
          </p>
          <div className="flex items-start gap-8 flex-wrap">
            <div className="shrink-0">
              <p
                className={`font-display text-6xl md:text-8xl tabular-nums leading-none ${
                  pct > 50 ? "text-ok" : "text-fail"
                }`}
              >
                {pct}%
              </p>
              <VitalLine
                status={pct > 50 ? "success" : "abandoned"}
                deathFrac={Math.max(pct / 100, 0.12)}
                height={24}
                className="mt-2"
              />
            </div>
            <div className="min-w-0 pt-1">
              <h1 className="font-display text-2xl md:text-3xl leading-snug">
                <span className="tabular-nums">
                  {survived} of {total}
                </span>{" "}
                personas completed “{report.task}”
              </h1>
              <p className="text-muted-foreground mt-2">
                <span className="tabular-nums">{total - survived}</span>{" "}
                abandoned the flow. Here is exactly where, and why.
              </p>
              <p className="text-xs font-mono text-muted-foreground mt-2 break-all">
                <span className="uppercase tracking-widest text-[10px]">
                  target
                </span>{" "}
                {report.target_url}
              </p>
            </div>
          </div>
        </div>
      </motion.header>

      {verdict && <AgentReadiness verdict={verdict} />}

      <div className="grid md:grid-cols-2 gap-5 items-start">
        <SurvivalCurve survival={report.survival} />
        <Heatmap
          points={report.heatmap_points}
          liveBackdrop={liveBackdrop}
          coordSpace={coordSpace}
        />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-2">
          Receipts
        </p>
        <h2 className="font-display text-2xl md:text-3xl">
          Exit interviews &amp; video receipts
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed mt-2">
          Grounded in each persona's real action trace — video, cloned-voice
          interview, and the moment they quit.
        </p>
      </motion.div>
      <div className="grid md:grid-cols-2 gap-5">
        {results.map((r, i) => (
          <ResultCard
            key={r.persona_id}
            result={r}
            name={nameOf(r.persona_id)}
            index={i}
          />
        ))}
        {results.length === 0 && (
          <p className="text-muted-foreground">
            No per-persona receipts in this report.
          </p>
        )}
      </div>

      <InsightsPanel />
    </div>
  );
}

function AgentReadiness({ verdict }: { verdict: AgentVerdict }) {
  const pass = verdict.status === "pass";
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className={`flex items-center gap-6 p-5 rounded-lg border ${
        pass ? "border-ok/40 bg-ok/10" : "border-fail/40 bg-fail/10"
      } max-sm:flex-col max-sm:items-start`}
    >
      <span
        className={`shrink-0 px-3 py-1.5 rounded-md font-mono text-xs uppercase tracking-widest ${
          pass ? "bg-ok" : "bg-fail"
        } text-background`}
      >
        {pass ? "Pass" : "Fail"}
      </span>
      <div className="min-w-0">
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
          Agent-readiness verdict
        </p>
        <p
          className={`font-display text-xl md:text-2xl mt-1 ${
            pass ? "text-ok" : "text-fail"
          }`}
        >
          {pass
            ? "An AI agent can complete this flow."
            : "An AI agent cannot complete this flow."}
        </p>
        <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
          {pass ? (
            <>
              <span className="text-foreground font-medium">{verdict.name}</span>{" "}
              completed the task in{" "}
              <span className="tabular-nums">{verdict.steps}</span> steps with no
              perturbation — your site is ready for computer-use agents.
            </>
          ) : (
            <>
              <span className="text-foreground font-medium">{verdict.name}</span>{" "}
              ran unimpaired and still failed (
              {OUTCOME_LABELS[verdict.outcome].toLowerCase()}) after{" "}
              <span className="tabular-nums">{verdict.steps}</span> steps — this
              flow is not yet agent-ready.
            </>
          )}
        </p>
      </div>
    </motion.section>
  );
}

function ResultCard({
  result,
  name,
  index,
}: {
  result: PersonaResult;
  name: string;
  index: number;
}) {
  const [videoOk, setVideoOk] = useState(true);
  const [audioOk, setAudioOk] = useState(true);
  const success = result.outcome === "success";
  const video = artifactUrl(result.video_path);
  const audio = artifactUrl(result.audio_path);

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.07 }}
      className="rounded-lg border border-border bg-panel overflow-hidden flex flex-col"
    >
      <header className="flex items-center gap-2 px-4 py-3 border-b border-hairline">
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            success ? "bg-ok" : "bg-fail"
          }`}
          aria-hidden="true"
        />
        <span className="text-sm font-medium truncate">{name}</span>
        <span
          className={`ml-auto font-mono text-[10px] uppercase tracking-widest whitespace-nowrap ${OUTCOME_TEXT_CLASS[result.outcome]}`}
        >
          {success ? "survived" : "died"}
          {result.failure_step != null && !success && (
            <> · step {result.failure_step}</>
          )}
          {result.duration_s ? (
            <>
              {" "}
              · {result.duration_s.toFixed(1)}s
            </>
          ) : null}
        </span>
      </header>

      <div className="flex flex-col gap-4 p-4">
        {!success && result.failure_reason && (
          <p className="font-mono text-xs leading-relaxed text-fail flex items-baseline gap-1.5">
            <span className="shrink-0" aria-hidden="true">
              &gt;
            </span>
            <span>
              {OUTCOME_LABELS[result.outcome].toLowerCase()} —{" "}
              “{result.failure_reason}”
              {result.failure_coords && (
                <span className="whitespace-nowrap">
                  {" "}
                  @ {result.failure_coords[0]},{result.failure_coords[1]}
                </span>
              )}
            </span>
          </p>
        )}

        <div>
          {video && videoOk ? (
            <video
              className={`viewport-bezel w-full rounded-md bg-background block aspect-[16/10] border ${
                success ? "border-ok" : "border-fail"
              }`}
              controls
              preload="metadata"
              onError={() => setVideoOk(false)}
              src={video}
            />
          ) : (
            <div className="viewport-bezel rounded-md border border-dashed border-border bg-background aspect-[16/10] flex flex-col items-center justify-center gap-1.5 text-muted-foreground">
              <p className="font-mono text-[10px] uppercase tracking-widest">
                Video receipt
              </p>
              <p className="font-mono text-[10px]">
                {video ? "unavailable (needs backend)" : "not recorded"}
              </p>
            </div>
          )}
        </div>

        <div>
          <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest mb-2">
            Exit interview{" "}
            <span className="normal-case tracking-normal">
              — in {name}'s cloned voice
            </span>
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
            <p className="rounded-md border border-dashed border-border bg-background px-3 py-2 font-mono text-[10px] text-muted-foreground text-center mb-3">
              Audio {audio ? "unavailable (needs backend)" : "not recorded"}
            </p>
          )}
          {result.transcript ? (
            <blockquote
              className={`border-l-2 pl-4 text-sm leading-relaxed ${
                success ? "border-ok/40" : "border-fail/40"
              }`}
            >
              “{result.transcript}”
            </blockquote>
          ) : (
            <p className="border-l-2 border-hairline pl-4 text-sm text-muted-foreground">
              No transcript recorded.
            </p>
          )}
        </div>
      </div>
    </motion.article>
  );
}
