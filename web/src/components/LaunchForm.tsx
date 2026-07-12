import { useEffect, useState } from "react";
import { listPersonas, startRun } from "../api";
import type { PersonaConfig } from "../types";

export default function LaunchForm({
  onLaunched,
  onOfflineDemo,
}: {
  onLaunched: (runId: string) => void;
  onOfflineDemo: () => void;
}) {
  const [personas, setPersonas] = useState<PersonaConfig[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [targetUrl, setTargetUrl] = useState("");
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listPersonas().then((ps) => {
      if (cancelled) return;
      setPersonas(ps);
      setSelected(new Set(ps.map((p) => p.id))); // everyone rides by default
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const canLaunch =
    targetUrl.trim() !== "" && task.trim() !== "" && selected.size > 0 && !busy;

  const launch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canLaunch) return;
    setBusy(true);
    setError(null);
    try {
      const runId = await startRun({
        target_url: targetUrl.trim(),
        task: task.trim(),
        persona_ids: [...selected],
      });
      onLaunched(runId);
    } catch (err) {
      setError(
        `Could not start the run — is the orchestrator up at the API base? (${String(err)})`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="launch">
      <div className="launch__hero">
        <h1 className="display">
          Watch your users <em>die</em>
        </h1>
        <p>
          Point a swarm of behaviorally-degraded synthetic users at a live page
          with a real goal. They either finish — or abandon at a specific pixel,
          on camera, and then tell you why.
        </p>
      </div>

      <form onSubmit={launch}>
        <div className="field">
          <label htmlFor="target-url">Target URL</label>
          <input
            id="target-url"
            type="url"
            placeholder="https://your-site.example/signup"
            value={targetUrl}
            onChange={(e) => setTargetUrl(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="task">Task</label>
          <input
            id="task"
            type="text"
            placeholder="Create an account and start the free trial."
            value={task}
            onChange={(e) => setTask(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label id="swarm-label">The swarm ({selected.size} selected)</label>
          <div
            className="persona-picker"
            role="group"
            aria-labelledby="swarm-label"
          >
            {personas.map((p) => (
              <button
                key={p.id}
                type="button"
                className="persona-chip"
                aria-pressed={selected.has(p.id)}
                onClick={() => toggle(p.id)}
              >
                <strong>{p.name}</strong>
                <span>{p.blurb}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="launch__actions">
          <button type="submit" className="btn btn--primary" disabled={!canLaunch}>
            {busy ? "Summoning…" : "Unleash the swarm"}
          </button>
          <button type="button" className="btn btn--ghostly" onClick={onOfflineDemo}>
            {"\u{1F47B}"} Offline demo — no backend needed
          </button>
        </div>
        {error && <p className="launch__error">{error}</p>}
      </form>
    </div>
  );
}
