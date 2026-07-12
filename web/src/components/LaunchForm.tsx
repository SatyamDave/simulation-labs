import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { listPersonas } from "../api";
import { PERSONA_CATALOG, type CatalogEntry } from "../personaCatalog";
import { perturbationBadges } from "../theme";

export interface LaunchValues {
  target_url: string;
  task: string;
  persona_ids: string[];
}

interface Props {
  onLaunch: (v: LaunchValues) => void;
  onOfflineDemo: () => void;
  busy?: boolean;
  error?: string | null;
}

// Real, public target examples plus the bundled hostile form (the torture test).
// Selecting a chip fills the URL and a matching task.
const EXAMPLES: {
  label: string;
  url: string;
  task: string;
  torture?: boolean;
}[] = [
  {
    label: "GitHub signup",
    url: "https://github.com/signup",
    task: "Create a new account and reach the verification step.",
  },
  {
    label: "Stripe register",
    url: "https://dashboard.stripe.com/register",
    task: "Create an account and start the setup.",
  },
  {
    label: "Hostile form",
    url: "http://localhost:8137/fixtures/hostile_form.html",
    task: "Create an account and submit the sign-up form.",
    torture: true,
  },
];

const INPUT_CLASS =
  "w-full px-5 py-4 text-base bg-background border border-border rounded-full outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-muted-foreground/40";

export function LaunchForm({ onLaunch, onOfflineDemo, busy, error }: Props) {
  const [url, setUrl] = useState("https://github.com/signup");
  const [task, setTask] = useState(
    "Create a new account and reach the verification step."
  );
  const [catalog, setCatalog] = useState<CatalogEntry[]>(PERSONA_CATALOG);
  const [selected, setSelected] = useState<string[]>(
    PERSONA_CATALOG.map((p) => p.id)
  );

  // Prefer the backend's live roster (GET /personas); the static catalog is
  // the offline/backendless fallback.
  useEffect(() => {
    let alive = true;
    listPersonas().then((live) => {
      if (!alive || !live) return;
      setCatalog(
        live.map((p) => ({ ...p, perturb: p.active_perturbations ?? [] }))
      );
      setSelected(live.map((p) => p.id));
    });
    return () => {
      alive = false;
    };
  }, []);

  function toggle(id: string) {
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id]
    );
  }

  const canLaunch = url.trim() && task.trim() && selected.length > 0 && !busy;

  return (
    <section className="px-6 pt-20 pb-24 relative overflow-hidden">
      {/* Animated background blobs (spec: Background & Decorative Effects) */}
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
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1 }}
        >
          {/* Eyebrow with live dot */}
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
              Behavioral user simulation
            </p>
          </motion.div>

          {/* Two-tone headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.8 }}
            className="text-5xl md:text-7xl font-light tracking-tight leading-[1.1] mb-8"
          >
            <span>See who fails your site,</span>
            <br />
            <span className="text-muted-foreground">before your users do.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="text-xl text-muted-foreground max-w-xl leading-relaxed mb-12"
          >
            A swarm of computer-use agents (H Company Holo) with{" "}
            <span className="text-foreground">mechanically degraded</span>{" "}
            perception and actuation attempts real tasks on any live site — and
            reports the exact point where real users give up.
          </motion.p>
        </motion.div>

        <motion.form
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
          className="flex flex-col gap-8"
          onSubmit={(e) => {
            e.preventDefault();
            if (canLaunch)
              onLaunch({
                target_url: url.trim(),
                task: task.trim(),
                persona_ids: selected,
              });
          }}
        >
          <div className="flex flex-col gap-3">
            <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
              Target URL
            </span>
            <input
              className={INPUT_CLASS}
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/signup"
              autoComplete="off"
              spellCheck={false}
            />
            <div className="flex flex-wrap gap-3">
              {EXAMPLES.map((ex) => (
                <motion.button
                  type="button"
                  key={ex.url}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className={`px-4 py-2 rounded-xl border text-sm font-medium transition-all border-border hover:border-border/80 text-muted-foreground hover:text-foreground flex items-center gap-2 ${
                    ex.torture ? "border-dashed" : ""
                  }`}
                  onClick={() => {
                    setUrl(ex.url);
                    setTask(ex.task);
                  }}
                  title={ex.url}
                >
                  {ex.label}
                  {ex.torture && (
                    <span className="text-xs font-mono uppercase tracking-wider">
                      torture test
                    </span>
                  )}
                </motion.button>
              ))}
            </div>
          </div>

          <label className="flex flex-col gap-3">
            <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
              Task
            </span>
            <input
              className={INPUT_CLASS}
              type="text"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Create a new account and reach the verification step."
            />
          </label>

          <div className="flex flex-col gap-3">
            <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
              The panel{" "}
              <span className="text-foreground tabular-nums">
                {selected.length}/{catalog.length} selected
              </span>
            </span>
            <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3">
              {catalog.map((p) => {
                const on = selected.includes(p.id);
                const badges = perturbationBadges(p);
                return (
                  <motion.button
                    type="button"
                    key={p.id}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className={`px-4 py-3 rounded-xl border text-left transition-all ${
                      on
                        ? "border-primary bg-primary/10"
                        : "border-border hover:border-border/80"
                    }`}
                    onClick={() => toggle(p.id)}
                    aria-pressed={on}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span
                        className={`text-sm font-medium truncate ${
                          on ? "text-primary" : "text-foreground"
                        }`}
                      >
                        {p.name}
                      </span>
                      {on ? (
                        <svg
                          className="w-4 h-4 text-emerald-500 shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-4 h-4 text-muted-foreground/40 shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 4v16m8-8H4"
                          />
                        </svg>
                      )}
                    </span>
                    <span className="block text-xs text-muted-foreground truncate mt-0.5">
                      {p.blurb}
                    </span>
                    <span className="flex flex-wrap gap-2 mt-2 min-h-4">
                      {badges.length ? (
                        badges.map((b) => (
                          <span
                            key={b.kind}
                            title={b.title}
                            className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider"
                          >
                            {b.text}
                          </span>
                        ))
                      ) : (
                        <span
                          className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider"
                          title="No perturbation — baseline"
                        >
                          baseline
                        </span>
                      )}
                    </span>
                  </motion.button>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              <span className="text-foreground font-medium">
                Mechanical fidelity, not roleplay:
              </span>{" "}
              blur = low vision · coordinate noise = tremor · tight budgets =
              impatience
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-500 border border-red-500/30 bg-red-500/5 rounded-2xl px-5 py-3">
              {error}
            </p>
          )}

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <motion.button
              type="submit"
              className="px-8 py-4 bg-foreground text-background rounded-full font-medium text-lg disabled:opacity-50"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              disabled={!canLaunch}
            >
              {busy ? "Starting simulation…" : "Run simulation"}
            </motion.button>
            <motion.button
              type="button"
              className="px-8 py-4 text-muted-foreground hover:text-foreground transition-colors text-lg flex items-center gap-2"
              whileHover={{ x: 5 }}
              onClick={onOfflineDemo}
            >
              Offline demo
              <motion.span
                animate={{ x: [0, 5, 0] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                →
              </motion.span>
            </motion.button>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed max-w-xl">
            Works on any live URL — public sites, staging, or the bundled
            hostile form. No backend? The{" "}
            <span className="text-foreground font-medium">Offline demo</span>{" "}
            replays a full run from local fixtures — completely self-contained.
          </p>
        </motion.form>
      </div>
    </section>
  );
}
