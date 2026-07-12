import { useState } from "react";
import type { PersonaResult, RunReport, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { API_BASE, artifactUrl } from "../api";
import { OUTCOME_COLOR } from "../theme";
import { SurvivalCurve } from "./SurvivalCurve";
import { Heatmap } from "./Heatmap";

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
    <div className="report">
      <header className="report__head">
        {onBack && (
          <button className="btn btn--ghost btn--sm" onClick={onBack}>
            ← Back to grid
          </button>
        )}
        <div className="report__headline">
          <div className="report__pct" style={{ color: pct > 50 ? OUTCOME_COLOR.success : OUTCOME_COLOR.stuck }}>
            {pct}%
          </div>
          <div className="report__headline-text">
            <div className="report__headline-main">
              {survived} of {total} personas completed “{report.task}”
            </div>
            <div className="report__headline-sub">
              {total - survived} abandoned the flow. Here is exactly where, and
              why.
            </div>
            <div className="report__url">{report.target_url}</div>
          </div>
        </div>
      </header>

      {verdict && <AgentReadiness verdict={verdict} />}

      <div className="report__charts">
        <SurvivalCurve survival={report.survival} />
        <Heatmap
          points={report.heatmap_points}
          liveBackdrop={liveBackdrop}
          coordSpace={coordSpace}
        />
      </div>

      <h2 className="report__section">Exit interviews & video receipts</h2>
      <p className="report__section-sub">
        Grounded in each persona's real action trace — video, cloned-voice
        interview, and the moment they quit.
      </p>
      <div className="report__results">
        {results.map((r) => (
          <ResultCard key={r.persona_id} result={r} name={nameOf(r.persona_id)} />
        ))}
        {results.length === 0 && (
          <p className="report__empty">No per-persona receipts in this report.</p>
        )}
      </div>
    </div>
  );
}

function AgentReadiness({ verdict }: { verdict: AgentVerdict }) {
  const pass = verdict.status === "pass";
  return (
    <section className={`verdict verdict--${verdict.status}`}>
      <div className="verdict__seal">{pass ? "PASS" : "FAIL"}</div>
      <div className="verdict__body">
        <div className="verdict__label">Agent-readiness verdict</div>
        <div className="verdict__head">
          {pass
            ? "An AI agent can complete this flow."
            : "An AI agent cannot complete this flow."}
        </div>
        <div className="verdict__sub">
          {pass ? (
            <>
              <b>{verdict.name}</b> completed the task in {verdict.steps} steps
              with no perturbation — your site is ready for computer-use agents.
            </>
          ) : (
            <>
              <b>{verdict.name}</b> ran unimpaired and still failed (
              {OUTCOME_LABELS[verdict.outcome].toLowerCase()}) after{" "}
              {verdict.steps} steps — this flow is not yet agent-ready.
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function ResultCard({ result, name }: { result: PersonaResult; name: string }) {
  const [videoOk, setVideoOk] = useState(true);
  const [audioOk, setAudioOk] = useState(true);
  const success = result.outcome === "success";
  const color = OUTCOME_COLOR[result.outcome];
  const video = artifactUrl(result.video_path);
  const audio = artifactUrl(result.audio_path);

  return (
    <article className="rcard" style={{ ["--accent" as string]: color }}>
      <header className="rcard__head">
        <span className="rcard__mark" style={{ background: color }}>
          {success ? "✓" : "✕"}
        </span>
        <div className="rcard__id">
          <div className="rcard__name">{name}</div>
          <div className="rcard__outcome" style={{ color }}>
            {OUTCOME_LABELS[result.outcome]}
            {result.failure_step != null && !success && (
              <> · gave up at step {result.failure_step}</>
            )}
            {result.duration_s ? (
              <> · {result.duration_s.toFixed(1)}s</>
            ) : null}
          </div>
        </div>
      </header>

      {!success && result.failure_reason && (
        <div className="rcard__reason">
          <span className="rcard__reason-label">Why they quit</span>
          {result.failure_reason}
          {result.failure_coords && (
            <span className="rcard__coords">
              @ {result.failure_coords[0]},{result.failure_coords[1]}
            </span>
          )}
        </div>
      )}

      <div className="rcard__body">
        <div className="rcard__video">
          {video && videoOk ? (
            <video
              controls
              preload="metadata"
              onError={() => setVideoOk(false)}
              src={video}
            />
          ) : (
            <div className="rcard__media-fallback">
              🎬 Video receipt
              <span>{video ? "unavailable (needs backend)" : "not recorded"}</span>
            </div>
          )}
        </div>

        <div className="rcard__interview">
          <div className="rcard__interview-label">
            🎙 Exit interview{" "}
            <span className="rcard__voice">in {name}'s cloned voice</span>
          </div>
          {audio && audioOk ? (
            <audio
              controls
              preload="none"
              onError={() => setAudioOk(false)}
              src={audio}
            />
          ) : (
            <div className="rcard__audio-fallback">
              🔇 Audio {audio ? "unavailable (needs backend)" : "not recorded"}
            </div>
          )}
          {result.transcript ? (
            <blockquote className="rcard__transcript">
              “{result.transcript}”
            </blockquote>
          ) : (
            <p className="rcard__transcript rcard__transcript--empty">
              No transcript recorded.
            </p>
          )}
        </div>
      </div>
    </article>
  );
}
