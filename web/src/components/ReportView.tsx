import { useState } from "react";
import { artifactUrl } from "../api";
import type { PersonaResult, RunReport } from "../types";
import Heatmap from "./Heatmap";
import SurvivalCurve, { OUTCOME_COLOR, OUTCOME_LABEL } from "./SurvivalCurve";

function VideoReceipt({
  result,
  name,
  offline,
}: {
  result: PersonaResult;
  name: string;
  offline: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const showVideo = result.video_path && !offline && !broken;
  return (
    <article className="receipt">
      {showVideo ? (
        <video
          controls
          preload="metadata"
          src={artifactUrl(result.video_path!)}
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="media-missing">
          {result.video_path
            ? "video receipt unavailable — backend offline"
            : "no video receipt"}
        </div>
      )}
      <div className="receipt__body">
        <div className="receipt__head">
          <span className="receipt__name">{name}</span>
          <span
            className="outcome-chip"
            style={{ color: OUTCOME_COLOR[result.outcome] }}
          >
            {OUTCOME_LABEL[result.outcome]}
          </span>
        </div>
        <div className="receipt__reason">
          {result.outcome === "success"
            ? `completed in ${result.duration_s ?? "?"}s`
            : result.failure_reason ||
              `abandoned after ${result.duration_s ?? "?"}s`}
          {result.failure_step != null &&
            result.failure_coords &&
            ` — died at step ${result.failure_step}, pixel (${result.failure_coords[0]}, ${result.failure_coords[1]})`}
        </div>
      </div>
    </article>
  );
}

function ExitInterview({
  result,
  name,
  offline,
}: {
  result: PersonaResult;
  name: string;
  offline: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const showAudio = result.audio_path && !offline && !broken;
  return (
    <article className="interview">
      <div className="interview__who">
        <span className="receipt__name">{name}</span>
        <span
          className="outcome-chip"
          style={{ color: OUTCOME_COLOR[result.outcome] }}
        >
          {OUTCOME_LABEL[result.outcome]}
        </span>
        {showAudio ? (
          <audio
            controls
            preload="none"
            src={artifactUrl(result.audio_path!)}
            onError={() => setBroken(true)}
          />
        ) : (
          <div
            className="media-missing"
            style={{ aspectRatio: "auto", marginTop: 10, padding: "12px 8px" }}
          >
            {result.audio_path
              ? "voice unavailable — backend offline"
              : "no audio"}
          </div>
        )}
      </div>
      <blockquote>
        “{result.transcript}”
        <footer>— exit interview, grounded in the real action trace</footer>
      </blockquote>
    </article>
  );
}

/**
 * The post-run report: completion-rate headline, survival curve, abandonment
 * heatmap over the target screenshot, video receipts, and voice exit-interviews.
 */
export default function ReportView({
  report,
  screenshotUrl,
  offline = false,
}: {
  report: RunReport;
  /** screenshot of the target page for the heatmap overlay */
  screenshotUrl: string;
  /** true when replaying fixtures with no backend — artifact media is skipped */
  offline?: boolean;
}) {
  const survival = report.survival ?? [];
  const results = report.results ?? [];
  const heatPoints = report.heatmap_points ?? [];
  const nameOf = (personaId: string) =>
    survival.find((s) => s.persona_id === personaId)?.persona_name ?? personaId;

  const rate = report.completion_rate ?? 0;
  const survivors = survival.filter((s) => s.completed).length;
  const interviews = results.filter((r) => r.transcript);

  return (
    <div className="report">
      <section>
        <div className="report__hero">
          <div
            className={`hero-number${rate < 0.5 ? " hero-number--grim" : ""}`}
            aria-label={`completion rate ${Math.round(rate * 100)} percent`}
          >
            {Math.round(rate * 100)}%
          </div>
          <div className="hero-sub">
            <div className="kicker">completion rate</div>
            <div className="big">
              <strong>
                {survivors} of {survival.length}
              </strong>{" "}
              personas survived “{report.task}” on{" "}
              <span style={{ wordBreak: "break-all" }}>{report.target_url}</span>
            </div>
          </div>
        </div>
      </section>

      {survival.length > 0 && (
        <section>
          <h3 className="section-title">Survival curve</h3>
          <p className="section-note">
            how deep each persona got before finishing or abandoning
          </p>
          <SurvivalCurve survival={survival} />
        </section>
      )}

      {heatPoints.length > 0 && (
        <section>
          <h3 className="section-title">Abandonment heatmap</h3>
          <p className="section-note">
            the exact pixels where personas gave up, on the real page
          </p>
          <Heatmap points={heatPoints} screenshotUrl={screenshotUrl} />
        </section>
      )}

      {results.length > 0 && (
        <section>
          <h3 className="section-title">Video receipts</h3>
          <p className="section-note">
            every claim above has a .webm behind it
          </p>
          <div className="receipts">
            {results.map((r) => (
              <VideoReceipt
                key={r.persona_id}
                result={r}
                name={nameOf(r.persona_id)}
                offline={offline}
              />
            ))}
          </div>
        </section>
      )}

      {interviews.length > 0 && (
        <section>
          <h3 className="section-title">Exit interviews</h3>
          <p className="section-note">
            each persona explains why, in its own voice — receipts, not vibes
          </p>
          {interviews.map((r) => (
            <ExitInterview
              key={r.persona_id}
              result={r}
              name={nameOf(r.persona_id)}
              offline={offline}
            />
          ))}
        </section>
      )}

      <p className="section-note">
        run {report.run_id}
        {report.generated_at ? ` · generated ${report.generated_at}` : ""}
        {report.contract_version ? ` · contracts v${report.contract_version}` : ""}
      </p>
    </div>
  );
}
