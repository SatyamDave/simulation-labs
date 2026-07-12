import { useState } from "react";
import { motion } from "framer-motion";
import { artifactUrl } from "../api";
import type { PersonaResult, RunReport } from "../types";
import Heatmap from "./Heatmap";
import SurvivalCurve, { OUTCOME_COLOR, OUTCOME_LABEL } from "./SurvivalCurve";

function OutcomeChip({ result }: { result: PersonaResult }) {
  return (
    <span
      className="text-xs font-mono uppercase tracking-wider px-2.5 py-0.5 rounded-full border border-current"
      style={{ color: OUTCOME_COLOR[result.outcome] }}
    >
      {OUTCOME_LABEL[result.outcome]}
    </span>
  );
}

function SectionHeader({
  eyebrow,
  title,
  note,
}: {
  eyebrow: string;
  title: string;
  note: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      className="mb-8"
    >
      <p className="text-sm font-mono text-muted-foreground mb-4">{eyebrow}</p>
      <h2 className="text-2xl md:text-3xl font-light mb-2">{title}</h2>
      <p className="text-sm text-muted-foreground leading-relaxed">{note}</p>
    </motion.div>
  );
}

function VideoReceipt({
  result,
  name,
  offline,
  index,
}: {
  result: PersonaResult;
  name: string;
  offline: boolean;
  index: number;
}) {
  const [broken, setBroken] = useState(false);
  const showVideo = result.video_path && !offline && !broken;
  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.1 }}
      whileHover={{ y: -8, transition: { duration: 0.2 } }}
      className="rounded-2xl border border-border bg-background overflow-hidden hover:border-foreground/30 hover:shadow-lg hover:shadow-foreground/5 transition-all duration-300"
    >
      {showVideo ? (
        <video
          className="w-full aspect-[16/10] block bg-muted"
          controls
          preload="metadata"
          src={artifactUrl(result.video_path!)}
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="flex items-center justify-center aspect-[16/10] bg-muted/30 text-xs font-mono text-muted-foreground uppercase tracking-wider text-center p-3">
          {result.video_path
            ? "video receipt unavailable — backend offline"
            : "no video receipt"}
        </div>
      )}
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-medium truncate">{name}</span>
          <OutcomeChip result={result} />
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed tabular-nums">
          {result.outcome === "success"
            ? `completed in ${result.duration_s ?? "?"}s`
            : result.failure_reason ||
              `abandoned after ${result.duration_s ?? "?"}s`}
          {result.failure_step != null &&
            result.failure_coords &&
            ` — abandoned at step ${result.failure_step}, pixel (${result.failure_coords[0]}, ${result.failure_coords[1]})`}
        </p>
      </div>
    </motion.article>
  );
}

function ExitInterview({
  result,
  name,
  offline,
  index,
}: {
  result: PersonaResult;
  name: string;
  offline: boolean;
  index: number;
}) {
  const [broken, setBroken] = useState(false);
  const showAudio = result.audio_path && !offline && !broken;
  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.1 }}
      className="grid md:grid-cols-[220px_1fr] gap-6 py-6 border-b border-border last:border-b-0"
    >
      <div>
        <span className="block text-sm font-medium mb-2">{name}</span>
        <OutcomeChip result={result} />
        {showAudio ? (
          <audio
            className="w-full mt-3"
            controls
            preload="none"
            src={artifactUrl(result.audio_path!)}
            onError={() => setBroken(true)}
          />
        ) : (
          <p className="mt-3 text-xs font-mono text-muted-foreground uppercase tracking-wider">
            {result.audio_path ? "voice unavailable — backend offline" : "no audio"}
          </p>
        )}
      </div>
      <blockquote className="border-l-2 border-foreground/10 pl-5 self-center">
        <p className="text-sm leading-relaxed text-muted-foreground mb-4">
          “{result.transcript}”
        </p>
        <footer className="text-xs text-muted-foreground">
          — exit interview, grounded in the real action trace
        </footer>
      </blockquote>
    </motion.article>
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
    <div>
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="pb-16"
      >
        <p className="text-sm font-mono text-muted-foreground mb-4">Report</p>
        <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
          <p
            className={`text-7xl md:text-8xl font-light tracking-tight tabular-nums leading-none ${
              rate < 0.5 ? "text-red-500" : ""
            }`}
            aria-label={`completion rate ${Math.round(rate * 100)} percent`}
          >
            {Math.round(rate * 100)}%
          </p>
          <div className="pb-1">
            <p className="text-xs text-muted-foreground mb-2">completion rate</p>
            <p className="text-lg font-light text-muted-foreground max-w-xl leading-relaxed">
              <span className="text-foreground tabular-nums">
                {survivors} of {survival.length}
              </span>{" "}
              personas survived “{report.task}” on{" "}
              <span className="break-all">{report.target_url}</span>
            </p>
          </div>
        </div>
      </motion.section>

      {survival.length > 0 && (
        <section className="py-16 border-t border-border/40">
          <SectionHeader
            eyebrow="Survival curve"
            title="How far each persona got"
            note="steps survived before finishing or abandoning"
          />
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <SurvivalCurve survival={survival} />
          </motion.div>
        </section>
      )}

      {heatPoints.length > 0 && (
        <section className="py-16 border-t border-border/40">
          <SectionHeader
            eyebrow="Abandonment heatmap"
            title="Where they gave up"
            note="the exact pixels where personas abandoned, on the real page"
          />
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <Heatmap points={heatPoints} screenshotUrl={screenshotUrl} />
          </motion.div>
        </section>
      )}

      {results.length > 0 && (
        <section className="py-16 border-t border-border/40">
          <SectionHeader
            eyebrow="Video receipts"
            title="Every claim has a recording"
            note="each session recorded end to end — receipts, not vibes"
          />
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {results.map((r, i) => (
              <VideoReceipt
                key={r.persona_id}
                result={r}
                name={nameOf(r.persona_id)}
                offline={offline}
                index={i}
              />
            ))}
          </div>
        </section>
      )}

      {interviews.length > 0 && (
        <section className="py-16 border-t border-border/40">
          <SectionHeader
            eyebrow="Exit interviews"
            title="Why they left, in their own words"
            note="each persona explains its outcome, grounded in its action trace"
          />
          <div>
            {interviews.map((r, i) => (
              <ExitInterview
                key={r.persona_id}
                result={r}
                name={nameOf(r.persona_id)}
                offline={offline}
                index={i}
              />
            ))}
          </div>
        </section>
      )}

      <p className="pt-8 border-t border-border/40 text-xs font-mono text-muted-foreground">
        run {report.run_id}
        {report.generated_at ? ` · generated ${report.generated_at}` : ""}
        {report.contract_version ? ` · contracts v${report.contract_version}` : ""}
      </p>
    </div>
  );
}
