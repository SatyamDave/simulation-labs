// Before/after comparison of two runs: pick another run from the server's
// index, then a side-by-side of Simulation Scores (big delta arrow), overlaid
// stepped survival curves (two validated categorical series), per-persona
// outcome pairs (dead -> alive highlighted) and the findings-count delta.

import { useEffect, useMemo, useState } from "react";
import { getLeaderboard, getReport, type LeaderboardEntry } from "../api";
import {
  computeFallbackInsights,
  fetchInsights,
  withDerivedStats,
  type RunInsights,
} from "../insights";
import type { RunReport, SurvivalPoint } from "../types";
import { OUTCOME_LABELS } from "../types";
import { CATEGORICAL, OUTCOME_COLOR, scoreColor } from "../theme";
import { SurvivalStepChart, timeAgo } from "./StatsPanel";

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
    <div className="report cmp">
      <header className="report__head">
        <div className="cmp__bar">
          <button className="btn btn--ghost btn--sm" onClick={onBack}>
            ← Back to report
          </button>
          {other && (
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => setOther(null)}
            >
              ⇄ Compare with a different run
            </button>
          )}
        </div>
        <div>
          <h2 className="report__section">Compare runs</h2>
          <p className="report__section-sub">
            Before/after for “{baseReport.task}” — did the fixes actually save
            anyone?
          </p>
        </div>
      </header>

      {!other ? (
        <div className="chart cmp__picker">
          <div className="chart__title">
            Compare with another run
            <span className="chart__sub">
              pick the baseline to measure this run against
            </span>
          </div>
          {listError && <div className="launch__error">⚠ {listError}</div>}
          {candidates === null && !listError && (
            <p className="report__empty">Loading runs…</p>
          )}
          {candidates !== null && candidates.length === 0 && (
            <p className="report__empty">
              No other finished runs on this server yet — run another
              simulation first.
            </p>
          )}
          {candidates !== null && candidates.length > 0 && (
            <div className="cmp__list">
              {candidates.map((c) => (
                <button
                  key={c.run_id}
                  className="cmp__cand"
                  onClick={() => pick(c.run_id)}
                  disabled={loadingId !== null}
                  title={c.task}
                >
                  <span className="cmp__cand-domain">
                    {domainOf(c.target_url)}
                  </span>
                  <span className="cmp__cand-task">{c.task}</span>
                  <span className="cmp__cand-meta">
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
          {loadError && <div className="launch__error">⚠ {loadError}</div>}
        </div>
      ) : (
        <SideBySide
          before={other}
          after={{ report: baseReport, insights: baseInsights }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The actual side-by-side
// ---------------------------------------------------------------------------
function ScoreHero({
  tag,
  run,
}: {
  tag: string;
  run: LoadedRun;
}) {
  return (
    <div className="insights__score">
      <div className="insights__score-label">{tag} · Simulation Score</div>
      <div
        className="insights__score-num"
        style={{ color: scoreColor(run.insights.ghostpanel_score) }}
      >
        {run.insights.ghostpanel_score}
        <span className="insights__score-denom">/100</span>
      </div>
      <div className="insights__score-sub">
        {domainOf(run.report.target_url)}
        {run.report.generated_at && <> · {timeAgo(run.report.generated_at)}</>}
        <br />
        {run.insights.summary}
      </div>
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
      <div className="cmp__heroes">
        <ScoreHero tag="Before" run={before} />
        <div
          className={`cmp__delta ${
            dScore > 0 ? "cmp__delta--up" : dScore < 0 ? "cmp__delta--down" : ""
          }`}
          title="Simulation Score change, before → after"
        >
          <span className="cmp__delta-arrow" aria-hidden="true">
            {dScore > 0 ? "▲" : dScore < 0 ? "▼" : "＝"}
          </span>
          <span className="cmp__delta-num">
            {dScore > 0 ? `+${dScore}` : dScore}
          </span>
          <span className="cmp__delta-lbl">score Δ</span>
        </div>
        <ScoreHero tag="After" run={after} />
      </div>

      <div className="statrow">
        <div className="stat stat--tile">
          <div
            className="stat__num"
            style={{
              color:
                dCompletion > 0
                  ? OUTCOME_COLOR.success
                  : dCompletion < 0
                  ? OUTCOME_COLOR.stuck
                  : undefined,
            }}
          >
            {dCompletion > 0 ? `+${dCompletion}` : dCompletion}pp
          </div>
          <div className="stat__lbl">completion Δ</div>
        </div>
        <div className="stat stat--tile">
          <div
            className="stat__num"
            style={{
              // Fewer findings is the improvement.
              color:
                dFindings < 0
                  ? OUTCOME_COLOR.success
                  : dFindings > 0
                  ? OUTCOME_COLOR.stuck
                  : undefined,
            }}
          >
            {dFindings > 0 ? `+${dFindings}` : dFindings}
          </div>
          <div className="stat__lbl">accessibility findings Δ</div>
        </div>
        <div className="stat stat--tile">
          <div className="stat__num">
            {before.insights.wcag_findings.length} →{" "}
            {after.insights.wcag_findings.length}
          </div>
          <div className="stat__lbl">findings before → after</div>
        </div>
      </div>

      {(beforeSeries.length > 0 || afterSeries.length > 0) && (
        <SurvivalStepChart
          title="Survival curves, overlaid"
          sub="personas still in the flow at each step — before vs after"
          series={[
            { label: "before", color: CATEGORICAL[0], points: beforeSeries },
            { label: "after", color: CATEGORICAL[1], points: afterSeries },
          ]}
        />
      )}

      <div className="chart">
        <div className="chart__title">
          Per-persona outcomes
          <span className="chart__sub">
            green rows are personas the changes brought back to life
          </span>
        </div>
        <div className="cmp__pairs">
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
                className={`cmp__pair ${gain ? "cmp__pair--gain" : ""} ${
                  loss ? "cmp__pair--loss" : ""
                }`}
              >
                <span className="cmp__pair-name">
                  {a?.persona_name || b?.persona_name || id}
                </span>
                <span
                  className="cmp__pair-outcome"
                  style={b ? { color: OUTCOME_COLOR[b.outcome] } : undefined}
                >
                  {b ? OUTCOME_LABELS[b.outcome] : "not in run"}
                </span>
                <span className="cmp__pair-arrow" aria-hidden="true">
                  →
                </span>
                <span
                  className="cmp__pair-outcome"
                  style={a ? { color: OUTCOME_COLOR[a.outcome] } : undefined}
                >
                  {a ? OUTCOME_LABELS[a.outcome] : "not in run"}
                </span>
                {gain && <span className="cmp__pair-tag">saved</span>}
                {loss && <span className="cmp__pair-tag cmp__pair-tag--loss">regressed</span>}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
