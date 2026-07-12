// Ghostpanel Index — the leaderboard of every run on this server, worst sites
// on top ("hall of shame"). Behavioral agent-readiness: measured, not declared.

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
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
  if (value == null) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="font-medium tabular-nums"
      style={{ color: scoreColor(value) }}
    >
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
    <motion.div
      className="mx-auto max-w-3xl"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <button
        type="button"
        className="text-sm text-muted-foreground hover:text-foreground transition-colors mb-10"
        onClick={onBack}
      >
        ← Back
      </button>

      <header>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Run index
        </h1>
        <p className="text-muted-foreground mt-2">
          Behavioral agent-readiness — measured, not declared. Worst sites on
          top.
        </p>
      </header>

      <div className="border-t border-border mt-10 pt-10">
        {error && (
          <p className="text-sm text-fail">
            Couldn't reach the backend ({error}). The index needs a running
            server.
          </p>
        )}

        {!error && rows === null && (
          <p className="text-sm text-muted-foreground">Loading runs…</p>
        )}

        {rows !== null && rows.length === 0 && (
          <div className="py-8 text-center flex flex-col items-center gap-5">
            <p className="text-sm text-muted-foreground">
              No runs indexed yet. Point the swarm at a site and see who
              survives.
            </p>
            <button
              type="button"
              className="px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
              onClick={onBack}
            >
              Run a simulation
            </button>
          </div>
        )}

        {rows !== null && rows.length > 0 && (
          <div className="gp-table-scroll">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>target</th>
                  <th
                    className="text-right"
                    title="Composite survival score, 0–100"
                  >
                    score
                  </th>
                  <th
                    className="text-right"
                    title="Did an unimpaired AI agent finish?"
                  >
                    agent-ready
                  </th>
                  <th className="text-right">completion</th>
                  <th className="text-right">personas</th>
                  <th className="text-right">when</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <span className="block text-sm font-medium">
                        {domainOf(r.target_url)}
                      </span>
                      <span
                        className="block text-xs text-muted-foreground truncate max-w-[36ch]"
                        title={r.task}
                      >
                        {r.task}
                      </span>
                    </td>
                    <td className="text-right font-mono text-xs">
                      <Score value={r.ghostpanel_score} />
                    </td>
                    <td className="text-right font-mono text-xs">
                      <Score value={r.agent_readiness_score} />
                    </td>
                    <td className="text-right font-mono text-xs tabular-nums">
                      {r.completion_rate != null
                        ? `${Math.round(r.completion_rate * 100)}%`
                        : "—"}
                    </td>
                    <td className="text-right font-mono text-xs tabular-nums">
                      {r.personas ?? "—"}
                    </td>
                    <td className="text-right font-mono text-xs text-muted-foreground whitespace-nowrap">
                      {timeAgo(r.generated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </motion.div>
  );
}
