// Before/after comparison of two runs: pick another run from the server's
// index, then a side-by-side of Simulation Scores (with the delta), overlaid
// stepped survival curves, per-persona outcome pairs (dead -> alive tagged)
// and the findings-count delta.

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { getLeaderboard, getReport, type LeaderboardEntry } from "../api";
import {
  computeFallbackInsights,
  fetchInsights,
  withDerivedStats,
  type RunInsights,
} from "../insights";
import type { RunReport, SurvivalPoint } from "../types";
import { OUTCOME_LABELS } from "../types";
import {
  OUTCOME_COLOR,
  scoreColor,
  SERIES_BASELINE,
  SERIES_CURRENT,
} from "../theme";
import { StatTile, SurvivalStepChart, timeAgo } from "./StatsPanel";

interface Props {
  baseReport: RunReport; // "this run" (the report the user came from)
  onBack: () => void;
}

interface LoadedRun {
  report: RunReport;
  insights: RunInsights;
}

function domainOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

async function loadRun(runId: string): Promise<LoadedRun> {
  const report = await getReport(runId);
  const insights =
    (await fetchInsights(runId)) ?? computeFallbackInsights(report);
  return { report, insights: withDerivedStats(insights, report) };
}

export function CompareView({ baseReport, onBack }: Props) {
  const [candidates, setCandidates] = useState<LeaderboardEntry[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [other, setOther] = useState<LoadedRun | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // "This run" insights: server copy when available, fallback otherwise.
  const baseFallback = useMemo(
    () => computeFallbackInsights(baseReport),
    [baseReport]
  );
  const [baseInsights, setBaseInsights] = useState<RunInsights>(baseFallback);
  useEffect(() => {
    let cancelled = false;
    setBaseInsights(baseFallback);
    fetchInsights(baseReport.run_id).then((ins) => {
      if (!cancelled && ins) {
        setBaseInsights(withDerivedStats(ins, baseReport));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [baseReport, baseFallback]);

  useEffect(() => {
    let cancelled = false;
    getLeaderboard()
      .then((rows) => {
        if (cancelled) return;
        setCandidates(rows.filter((r) => r.run_id !== baseReport.run_id));
      })
      .catch((err) => {
        if (!cancelled) setListError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [baseReport.run_id]);

  async function pick(runId: string) {
    setLoadingId(runId);
    setLoadError(null);
    try {
      setOther(await loadRun(runId));
    } catch (err) {
      setLoadError(`Couldn't load run ${runId}: ${String(err)}`);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <motion.div
      className="mx-auto max-w-3xl"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex items-center gap-6 mb-10">
        <button
          type="button"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          onClick={onBack}
        >
          ← Back to the report
        </button>
        {other && (
          <button
            type="button"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setOther(null)}
          >
            compare with a different run →
          </button>
        )}
      </div>

      <header>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Compare runs
        </h1>
        <p className="text-muted-foreground mt-2">
          Before/after for “{baseReport.task}” — did the fixes actually save
          anyone?
        </p>
      </header>

      {!other ? (
        <section className="border-t border-border mt-10 pt-10">
          <div className="mb-5">
            <h2 className="text-lg font-semibold">Pick the baseline</h2>
            <p className="text-sm text-muted-foreground mt-1">
              The run you pick reads as “before”; this run is “after”.
            </p>
          </div>
          {listError && <p className="text-sm text-fail">{listError}</p>}
          {candidates === null && !listError && (
            <p className="text-sm text-muted-foreground">Loading runs…</p>
          )}
          {candidates !== null && candidates.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No other finished runs on this server yet — run another
              simulation first.
            </p>
          )}
          {candidates !== null && candidates.length > 0 && (
            <div className="flex flex-col gap-2">
              {candidates.map((c) => (
                <button
                  type="button"
                  key={c.run_id}
                  className="px-4 py-3 rounded-xl border border-border text-left hover:bg-hover transition-colors disabled:opacity-40 flex flex-wrap items-baseline gap-x-3 gap-y-1 min-w-0"
                  onClick={() => pick(c.run_id)}
                  disabled={loadingId !== null}
                  title={c.task}
                >
                  <span className="text-sm font-medium">
                    {domainOf(c.target_url)}
                  </span>
                  <span className="text-xs text-muted-foreground truncate">
                    {c.task}
                  </span>
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground whitespace-nowrap tabular-nums">
                    {c.ghostpanel_score != null && (
                      <b style={{ color: scoreColor(c.ghostpanel_score) }}>
                        {c.ghostpanel_score}
                      </b>
                    )}
                    {c.completion_rate != null && (
                      <> · {Math.round(c.completion_rate * 100)}%</>
                    )}
                    {c.generated_at && <> · {timeAgo(c.generated_at)}</>}
                    {loadingId === c.run_id && <> · loading…</>}
                  </span>
                </button>
              ))}
            </div>
          )}
          {loadError && <p className="text-sm text-fail mt-4">{loadError}</p>}
        </section>
      ) : (
        <SideBySide
          before={other}
          after={{ report: baseReport, insights: baseInsights }}
        />
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// The actual side-by-side
// ---------------------------------------------------------------------------
function ScoreHero({ tag, run }: { tag: string; run: LoadedRun }) {
  return (
    <div className="min-w-0">
      <p className="font-mono text-[11px] text-muted-foreground">
        {tag} · simulation score
      </p>
      <p
        className="text-5xl font-semibold tracking-tight tabular-nums leading-none mt-2"
        style={{ color: scoreColor(run.insights.ghostpanel_score) }}
      >
        {run.insights.ghostpanel_score}
        <span className="text-xl text-muted-foreground font-normal">/100</span>
      </p>
      <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
        {domainOf(run.report.target_url)}
        {run.report.generated_at && <> · {timeAgo(run.report.generated_at)}</>}
        <br />
        {run.insights.summary}
      </p>
    </div>
  );
}

function SideBySide({ before, after }: { before: LoadedRun; after: LoadedRun }) {
  const dScore =
    after.insights.ghostpanel_score - before.insights.ghostpanel_score;
  const dFindings =
    after.insights.wcag_findings.length - before.insights.wcag_findings.length;
  const dCompletion = Math.round(
    100 * ((after.report.completion_rate ?? 0) - (before.report.completion_rate ?? 0))
  );

  // Per-persona pairs, in the after-run's order; unmatched personas ride along.
  const byId = (rows: SurvivalPoint[]) =>
    new Map(rows.map((s) => [s.persona_id, s]));
  const beforeById = byId(before.report.survival);
  const ids = [
    ...after.report.survival.map((s) => s.persona_id),
    ...before.report.survival
      .map((s) => s.persona_id)
      .filter((id) => !after.report.survival.some((s) => s.persona_id === id)),
  ];

  const beforeSeries = before.insights.survival_series ?? [];
  const afterSeries = after.insights.survival_series ?? [];

  return (
    <>
      <section className="border-t border-border mt-10 pt-10">
        <div className="grid sm:grid-cols-[1fr_auto_1fr] items-start gap-8">
          <ScoreHero tag="before" run={before} />
          <div
            className="self-center text-center"
            title="Simulation Score change, before → after"
          >
            <p
              className="text-2xl font-semibold tabular-nums"
              style={{
                color:
                  dScore > 0
                    ? "var(--ok)"
                    : dScore < 0
                      ? "var(--fail)"
                      : undefined,
              }}
            >
              {dScore > 0 ? `+${dScore}` : dScore}
            </p>
            <p className="font-mono text-[11px] text-muted-foreground mt-0.5">
              score Δ
            </p>
          </div>
          <ScoreHero tag="after" run={after} />
        </div>
      </section>

      <section className="border-t border-border mt-12 pt-10">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-6">
          <StatTile
            label="completion Δ"
            value={`${dCompletion > 0 ? `+${dCompletion}` : dCompletion}pp`}
            color={
              dCompletion > 0
                ? OUTCOME_COLOR.success
                : dCompletion < 0
                  ? OUTCOME_COLOR.stuck
                  : undefined
            }
          />
          <StatTile
            label="accessibility findings Δ"
            value={String(dFindings > 0 ? `+${dFindings}` : dFindings)}
            // Fewer findings is the improvement.
            color={
              dFindings < 0
                ? OUTCOME_COLOR.success
                : dFindings > 0
                  ? OUTCOME_COLOR.stuck
                  : undefined
            }
          />
          <StatTile
            label="findings before → after"
            value={`${before.insights.wcag_findings.length} → ${after.insights.wcag_findings.length}`}
          />
        </div>
      </section>

      {(beforeSeries.length > 0 || afterSeries.length > 0) && (
        <section className="border-t border-border mt-12 pt-10">
          <SurvivalStepChart
            title="Survival curves, overlaid"
            sub="personas still in the flow at each step — before vs after"
            series={[
              { label: "before", color: SERIES_BASELINE, points: beforeSeries },
              { label: "after", color: SERIES_CURRENT, points: afterSeries },
            ]}
          />
        </section>
      )}

      <section className="border-t border-border mt-12 pt-10">
        <div className="mb-5">
          <h2 className="text-lg font-semibold">Per-persona outcomes</h2>
          <p className="text-sm text-muted-foreground mt-1">
            “saved” marks personas the changes brought back to life.
          </p>
        </div>
        <div className="flex flex-col">
          {ids.map((id) => {
            const b = beforeById.get(id);
            const a = after.report.survival.find((s) => s.persona_id === id);
            const bDone = Boolean(b && (b.completed || b.outcome === "success"));
            const aDone = Boolean(a && (a.completed || a.outcome === "success"));
            const gain = b != null && a != null && !bDone && aDone;
            const loss = b != null && a != null && bDone && !aDone;
            return (
              <div
                key={id}
                className="grid grid-cols-[minmax(110px,160px)_1fr_auto_1fr_auto] items-baseline gap-3 py-2.5 border-b border-border last:border-b-0 max-sm:grid-cols-[1fr_auto_1fr_auto]"
              >
                <span className="text-sm font-medium truncate max-sm:col-span-4">
                  {a?.persona_name || b?.persona_name || id}
                </span>
                <span
                  className="font-mono text-[11px] whitespace-nowrap"
                  style={b ? { color: OUTCOME_COLOR[b.outcome] } : undefined}
                >
                  {b ? OUTCOME_LABELS[b.outcome] : "not in run"}
                </span>
                <span
                  className="font-mono text-[11px] text-muted-foreground"
                  aria-hidden="true"
                >
                  →
                </span>
                <span
                  className="font-mono text-[11px] whitespace-nowrap"
                  style={a ? { color: OUTCOME_COLOR[a.outcome] } : undefined}
                >
                  {a ? OUTCOME_LABELS[a.outcome] : "not in run"}
                </span>
                <span className="font-mono text-[11px] whitespace-nowrap justify-self-end">
                  {gain && <span className="text-ok">saved</span>}
                  {loss && <span className="text-fail">regressed</span>}
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
