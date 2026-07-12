// Ghostpanel Index — the leaderboard of every run on this server, worst sites
// on top ("hall of shame"). Behavioral agent-readiness: measured, not declared.

import { useEffect, useState } from "react";
import { getLeaderboard, type LeaderboardEntry } from "../api";
import { scoreColor } from "../theme";
import { timeAgo } from "./StatsPanel";

interface Props {
  onBack: () => void; // back to the launch screen (also the empty-state CTA)
}

function domainOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

function Score({ value }: { value?: number | null }) {
  if (value == null) return <span className="index__na">—</span>;
  return (
    <span className="index__score" style={{ color: scoreColor(value) }}>
      {value}
    </span>
  );
}

export function IndexView({ onBack }: Props) {
  const [rows, setRows] = useState<LeaderboardEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLeaderboard()
      .then((entries) => {
        if (cancelled) return;
        // Hall of shame: worst score first; unscored rows sink to the bottom.
        setRows(
          [...entries].sort((a, b) => {
            const as = a.ghostpanel_score ?? Number.POSITIVE_INFINITY;
            const bs = b.ghostpanel_score ?? Number.POSITIVE_INFINITY;
            return as - bs;
          })
        );
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="report index">
      <header className="report__head">
        <div>
          <button className="btn btn--ghost btn--sm" onClick={onBack}>
            ← Back
          </button>
        </div>
        <div>
          <h2 className="report__section">📊 Ghostpanel Index</h2>
          <p className="report__section-sub">
            Behavioral agent-readiness — measured, not declared. Worst sites on
            top.
          </p>
        </div>
      </header>

      {error && (
        <div className="launch__error">
          ⚠ Couldn't reach the backend ({error}). The Index needs a running
          server.
        </div>
      )}

      {!error && rows === null && <p className="report__empty">Loading runs…</p>}

      {rows !== null && rows.length === 0 && (
        <div className="index__empty">
          <p>
            No runs indexed yet. Point the swarm at a site and see who
            survives.
          </p>
          <button className="btn btn--primary" onClick={onBack}>
            Run a simulation →
          </button>
        </div>
      )}

      {rows !== null && rows.length > 0 && (
        <div className="chart">
          <div className="insights__wcag-scroll">
            <table className="insights__table index__table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th title="Composite survival score, 0–100">Score</th>
                  <th title="Did an unimpaired AI agent finish?">
                    Agent-ready
                  </th>
                  <th>Completion</th>
                  <th>Personas</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <span className="index__domain">
                        {domainOf(r.target_url)}
                      </span>
                      <span className="index__task" title={r.task}>
                        {r.task}
                      </span>
                    </td>
                    <td className="pstats__num">
                      <Score value={r.ghostpanel_score} />
                    </td>
                    <td className="pstats__num">
                      <Score value={r.agent_readiness_score} />
                    </td>
                    <td className="pstats__num">
                      {r.completion_rate != null
                        ? `${Math.round(r.completion_rate * 100)}%`
                        : "—"}
                    </td>
                    <td className="pstats__num">{r.personas ?? "—"}</td>
                    <td className="pstats__num index__when">
                      {timeAgo(r.generated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
