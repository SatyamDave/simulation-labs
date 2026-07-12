import { useEffect, useMemo, useState } from "react";
import type { PersonaResult, RunReport, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import { API_BASE, artifactUrl } from "../api";
import { OUTCOME_COLOR, scoreColor } from "../theme";
import {
  computeFallbackInsights,
  fetchInsights,
  withDerivedStats,
  type AgentReadiness,
  type RunInsights,
  type WcagFinding,
} from "../insights";
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
  const insights = withDerivedStats(
    serverInsights ?? fallbackInsights,
    report
  );

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
        {(onBack || onCompare) && (
          <div className="report__nav">
            {onBack && (
              <button className="btn btn--ghost btn--sm" onClick={onBack}>
                ← Back to grid
              </button>
            )}
            {onCompare && (
              <button className="btn btn--ghost btn--sm" onClick={onCompare}>
                ⇄ Compare with another run
              </button>
            )}
          </div>
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

      {live && <PolicyPanel />}

      <InsightsPanel insights={insights} />

      <StatsPanel insights={insights} />

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

      <WhyItMatters />
    </div>
  );
}

// Report footer, small print: the market context in hard numbers, with the
// source named inline for each claim.
function WhyItMatters() {
  return (
    <details className="whyit">
      <summary>Why this matters — the market in four numbers</summary>
      <ul>
        <li>
          <b>2,019</b> US digital-accessibility lawsuits were filed in H1 2025
          alone <span className="whyit__src">(UsableNet)</span>.
        </li>
        <li>
          The <b>EU Accessibility Act</b> has been in force since June 2025 —
          EN&nbsp;301&nbsp;549 conformity gives a legal presumption of
          conformity <span className="whyit__src">(Directive (EU) 2019/882)</span>.
        </li>
        <li>
          Prompt-based LLM personas reproduce real user actions at only{" "}
          <b>11.86%</b> <span className="whyit__src">(arXiv 2503.20749)</span> —
          Ghostpanel degrades the perception channel mechanically instead of
          asking a model to roleplay.
        </li>
        <li>
          Cloudflare's Agent Readiness Score scans what sites <i>declare</i>;
          Ghostpanel measures what agents <b>survive</b>.
        </li>
      </ul>
    </details>
  );
}

function InsightsPanel({ insights }: { insights: RunInsights }) {
  return (
    <section className="insights">
      <div className="insights__hero">
        <div className="insights__score">
          <div className="insights__score-label">Simulation Score</div>
          <div
            className="insights__score-num"
            style={{ color: scoreColor(insights.ghostpanel_score) }}
          >
            {insights.ghostpanel_score}
            <span className="insights__score-denom">/100</span>
          </div>
          <div className="insights__score-sub">{insights.summary}</div>
        </div>
        {insights.agent_readiness && (
          <AgentReadinessStat agent={insights.agent_readiness} />
        )}
      </div>
      <WcagEvidence findings={insights.wcag_findings} />
    </section>
  );
}

function AgentReadinessStat({ agent }: { agent: AgentReadiness }) {
  const pass = agent.outcome === "success";
  return (
    <div className={`verdict verdict--${pass ? "pass" : "fail"}`}>
      <div className="verdict__seal">{pass ? "PASS" : "FAIL"}</div>
      <div className="verdict__body">
        <div className="verdict__label">Agent readiness</div>
        <div className="verdict__head">Can an AI agent use your site?</div>
        <div className="verdict__sub">
          <b>
            {agent.score}
            /100
          </b>{" "}
          · {OUTCOME_LABELS[agent.outcome]} · {agent.steps} steps
          {agent.note && <> — {agent.note}</>}
        </div>
      </div>
    </div>
  );
}

function WcagEvidence({ findings }: { findings: WcagFinding[] }) {
  return (
    <div className="insights__wcag">
      <h3 className="insights__wcag-title">Accessibility evidence</h3>
      <p className="insights__wcag-caption">
        Each row is evidenced by a video receipt and an exact failure pixel —
        WCAG 2.2 / EN 301 549 mapping.
      </p>
      {findings.length === 0 ? (
        <div className="insights__wcag-clear">
          ✓ No accessibility failures evidenced in this run.
        </div>
      ) : (
        <div className="insights__wcag-scroll">
          <table className="insights__table">
            <thead>
              <tr>
                <th>Persona</th>
                <th>WCAG 2.2 criterion</th>
                <th>EN 301 549</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f, i) => (
                <tr key={`${f.persona_id}-${f.criterion}-${i}`}>
                  <td className="insights__td-persona">{f.persona_name}</td>
                  <td className="insights__td-criterion">
                    <span className="insights__crit">{f.criterion}</span>{" "}
                    {f.name}
                    <span className="insights__level">{f.level}</span>
                  </td>
                  <td className="insights__td-en">{f.standard_ref}</td>
                  <td className="insights__td-evidence">
                    {f.evidence}
                    {f.failure_step != null && (
                      <span className="insights__step">
                        step {f.failure_step}
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
