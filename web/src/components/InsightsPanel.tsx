import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getInsights } from "../api";
import type { Insight } from "../types";

type LoadState = "loading" | "ready" | "empty";

// Cross-run insights — what the swarm has learned across sites. Fetches the
// knowledge base on mount; fetch errors degrade quietly to the empty state.
export function InsightsPanel() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [status, setStatus] = useState<LoadState>("loading");

  useEffect(() => {
    let alive = true;
    getInsights()
      .then((rows) => {
        if (!alive) return;
        setInsights(rows);
        setStatus(rows.length ? "ready" : "empty");
      })
      .catch(() => {
        if (!alive) return;
        setStatus("empty");
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      className="flex flex-col gap-5"
    >
      <div>
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-2">
          Memory layer
        </p>
        <h2 className="font-display text-2xl md:text-3xl">
          Cross-run insights — what the swarm has learned across sites
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed mt-2">
          Durable lessons distilled from every prior run, tagged by the
          impairment that surfaced them.
        </p>
      </div>

      {status === "loading" && (
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          loading insights…
        </span>
      )}

      {status === "empty" && (
        <p className="rounded-lg border border-dashed border-border bg-panel px-4 py-6 text-sm text-muted-foreground text-center">
          No cross-run insights yet — run more sessions to build the knowledge
          base.
        </p>
      )}

      {status === "ready" && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {insights.map((ins, i) => (
            <InsightCard key={`${ins.persona_id}-${i}`} insight={ins} index={i} />
          ))}
        </div>
      )}
    </motion.section>
  );
}

function InsightCard({ insight, index }: { insight: Insight; index: number }) {
  const success = insight.outcome === "success";
  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.05 }}
      className="rounded-lg border border-border bg-panel overflow-hidden flex flex-col"
    >
      <header className="flex items-center gap-2 px-4 py-3 border-b border-hairline">
        <span className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest border border-hairline rounded-sm px-1.5 py-0.5 whitespace-nowrap">
          {insight.impairment}
        </span>
        <span
          className={`ml-auto font-mono text-[10px] uppercase tracking-widest whitespace-nowrap ${
            success ? "text-ok" : "text-muted-foreground"
          }`}
        >
          {insight.outcome}
          {insight.steps_survived != null && (
            <> · {insight.steps_survived} steps</>
          )}
        </span>
      </header>

      <div className="flex flex-col gap-3 p-4">
        <p className="text-sm leading-relaxed">{insight.content}</p>
        <div className="mt-auto flex items-center gap-2 text-xs font-mono text-muted-foreground min-w-0">
          <span className="text-foreground truncate">
            {insight.persona_name}
          </span>
          <span aria-hidden="true">·</span>
          <span className="truncate">{insight.site}</span>
          {insight.score != null && (
            <span className="ml-auto tabular-nums whitespace-nowrap">
              {insight.score.toFixed(2)}
            </span>
          )}
        </div>
      </div>
    </motion.article>
  );
}
