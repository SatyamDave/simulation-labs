import { useEffect, useState } from "react";
import { motion } from "framer-motion";
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
    <section className="px-6 pt-24 pb-32 relative overflow-hidden">
      {/* slow background blobs — launch hero only */}
      <div className="absolute inset-0 -z-10">
        <motion.div
          className="absolute top-1/4 -left-1/4 w-1/2 h-1/2 rounded-full bg-primary/5 blur-3xl"
          animate={{ x: [0, 50, 0], y: [0, 30, 0] }}
          transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute bottom-1/4 -right-1/4 w-1/2 h-1/2 rounded-full bg-primary/5 blur-3xl"
          animate={{ x: [0, -50, 0], y: [0, -30, 0] }}
          transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="container mx-auto max-w-4xl">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="flex items-center gap-2 mb-6"
          >
            <motion.div
              className="w-2 h-2 rounded-full bg-emerald-500"
              animate={{ scale: [1, 1.2, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <p className="text-sm font-mono text-muted-foreground">
              Behavioral synthetic users
            </p>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.8 }}
            className="text-5xl md:text-7xl font-light tracking-tight leading-[1.1] mb-8"
          >
            <span>Watch your users struggle,</span>
            <br />
            <span className="text-muted-foreground">before they're real.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="text-xl text-muted-foreground max-w-xl leading-relaxed mb-12"
          >
            Point a swarm of behaviorally-degraded synthetic users at a live
            page with a real goal. They either finish — or abandon at a
            specific pixel, on camera, and then tell you why.
          </motion.p>
        </motion.div>

        <motion.form
          onSubmit={launch}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
        >
          <div className="mb-6">
            <label htmlFor="target-url" className="block text-sm font-medium mb-2">
              Target URL
            </label>
            <input
              id="target-url"
              type="url"
              placeholder="https://your-site.example/signup"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              required
              className="w-full px-5 py-4 text-base bg-background border border-border rounded-full outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-muted-foreground/40"
            />
          </div>
          <div className="mb-6">
            <label htmlFor="task" className="block text-sm font-medium mb-2">
              Task
            </label>
            <input
              id="task"
              type="text"
              placeholder="Create an account and start the free trial."
              value={task}
              onChange={(e) => setTask(e.target.value)}
              required
              className="w-full px-5 py-4 text-base bg-background border border-border rounded-full outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-muted-foreground/40"
            />
          </div>
          <div className="mb-6">
            <span id="swarm-label" className="block text-sm font-medium mb-2">
              The swarm{" "}
              <span className="text-muted-foreground tabular-nums">
                ({selected.size} selected)
              </span>
            </span>
            <div
              className="grid sm:grid-cols-2 md:grid-cols-3 gap-3"
              role="group"
              aria-labelledby="swarm-label"
            >
              {personas.map((p) => {
                const on = selected.has(p.id);
                return (
                  <motion.button
                    key={p.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggle(p.id)}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className={`px-4 py-3 rounded-xl border text-left transition-all ${
                      on
                        ? "border-primary bg-primary/10"
                        : "border-border hover:border-border/80"
                    }`}
                  >
                    <span
                      className={`block text-sm font-medium ${
                        on ? "text-primary" : "text-foreground"
                      }`}
                    >
                      {p.name}
                    </span>
                    <span className="block text-xs text-muted-foreground mt-0.5">
                      {p.blurb}
                    </span>
                  </motion.button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mt-10">
            <motion.button
              type="submit"
              disabled={!canLaunch}
              className="px-8 py-4 bg-foreground text-background rounded-full font-medium text-lg disabled:opacity-50 disabled:cursor-not-allowed"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {busy ? "Launching…" : "Launch the swarm"}
            </motion.button>
            <motion.button
              type="button"
              onClick={onOfflineDemo}
              className="px-8 py-4 text-muted-foreground hover:text-foreground transition-colors text-lg flex items-center gap-2"
              whileHover={{ x: 5 }}
            >
              Run the offline demo
              <motion.span
                animate={{ x: [0, 5, 0] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                →
              </motion.span>
            </motion.button>
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            The offline demo replays fixture data — no backend needed.
          </p>
          {error && <p className="mt-4 text-sm text-red-500">{error}</p>}
        </motion.form>
      </div>
    </section>
  );
}
