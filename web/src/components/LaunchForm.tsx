import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { listPersonas } from "../api";
import { PERSONA_CATALOG, type CatalogEntry } from "../personaCatalog";
import { perturbationBadges } from "../theme";
import type { MemoryMode } from "../types";

export interface LaunchValues {
  target_url: string;
  task: string;
  persona_ids: string[];
  memory_mode: MemoryMode;
}

// Memory-layer options for the launch selector. `helper` is the one-line
// tradeoff shown under the active choice.
const MEMORY_MODES: {
  value: MemoryMode;
  label: string;
  helper: string;
}[] = [
  {
    value: "off",
    label: "Off (fresh users)",
    helper:
      "Honest research runs — personas behave as first-time users with no prior knowledge.",
  },
  {
    value: "site_hints",
    label: "Site hints",
    helper:
      "Reuse what past runs learned about this site — faster, fewer steps to the goal.",
  },
  {
    value: "returning_user",
    label: "Returning users",
    helper: "Each persona also recalls its own prior visits to this site.",
  },
];

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
  "w-full px-3 py-2.5 font-mono text-sm bg-background border border-border rounded-md outline-none focus:border-live/60 focus:ring-2 focus:ring-live/15 transition-colors placeholder:text-muted-foreground/40";

const FIELD_LABEL =
  "text-[10px] font-mono text-muted-foreground uppercase tracking-widest";

export function LaunchForm({ onLaunch, onOfflineDemo, busy, error }: Props) {
  const [url, setUrl] = useState("https://github.com/signup");
  const [task, setTask] = useState(
    "Create a new account and reach the verification step."
  );
  const [catalog, setCatalog] = useState<CatalogEntry[]>(PERSONA_CATALOG);
  const [selected, setSelected] = useState<string[]>(
    PERSONA_CATALOG.map((p) => p.id)
  );
  const [memoryMode, setMemoryMode] = useState<MemoryMode>("off");

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
    <section className="px-6 pt-14 pb-20 md:pt-20">
      <div className="container mx-auto max-w-6xl grid md:grid-cols-[minmax(0,10fr)_minmax(0,11fr)] gap-10 lg:gap-16 items-start">
        {/* Left column — the thesis */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="flex items-center gap-2 mb-6">
            <motion.span
              className="w-1.5 h-1.5 rounded-full bg-live"
              animate={{ opacity: [1, 0.35, 1] }}
              transition={{ duration: 1.6, repeat: Infinity }}
            />
            <p className="text-xs font-mono text-muted-foreground uppercase tracking-widest">
              Behavioral user simulation
            </p>
          </div>

          <h1 className="font-display text-4xl md:text-5xl lg:text-[3.4rem] leading-[1.05] mb-6">
            See who fails your site,
            <br />
            <span className="text-muted-foreground">
              before your users do.
            </span>
          </h1>

          <p className="text-base md:text-lg text-muted-foreground max-w-lg leading-relaxed mb-8">
            A swarm of computer-use agents (H Company Holo) with{" "}
            <span className="text-foreground">mechanically degraded</span>{" "}
            perception and actuation attempts real tasks on your live site —
            and reports the exact pixel where each one gives up.
          </p>

          <div className="border-t border-hairline pt-5">
            <p className={`${FIELD_LABEL} mb-3`}>
              Mechanical fidelity, not roleplay
            </p>
            <dl className="font-mono text-xs text-muted-foreground grid grid-cols-[auto_auto_1fr] gap-x-3 gap-y-1.5">
              <dt className="text-foreground">blur</dt>
              <dd aria-hidden="true">→</dd>
              <dd>low vision</dd>
              <dt className="text-foreground">coordinate noise</dt>
              <dd aria-hidden="true">→</dd>
              <dd>hand tremor</dd>
              <dt className="text-foreground">tight budgets</dt>
              <dd aria-hidden="true">→</dd>
              <dd>impatience</dd>
            </dl>
          </div>
        </motion.div>

        {/* Right column — mission config bezel */}
        <motion.form
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.12 }}
          className="rounded-lg border border-border bg-panel-raised overflow-hidden"
          onSubmit={(e) => {
            e.preventDefault();
            if (canLaunch)
              onLaunch({
                target_url: url.trim(),
                task: task.trim(),
                persona_ids: selected,
                memory_mode: memoryMode,
              });
          }}
        >
          <div className="flex items-center justify-between px-5 py-2.5 border-b border-hairline">
            <span className={FIELD_LABEL}>Mission config</span>
            <span
              className="font-mono text-[10px] text-muted-foreground/60 tabular-nums"
              aria-hidden="true"
            >
              SL-01
            </span>
          </div>

          <div className="flex flex-col gap-6 p-5">
            <div className="flex flex-col gap-2">
              <span className={FIELD_LABEL}>Target URL</span>
              <input
                className={INPUT_CLASS}
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/signup"
                autoComplete="off"
                spellCheck={false}
              />
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((ex) => (
                  <button
                    type="button"
                    key={ex.url}
                    className={`px-2.5 py-1.5 rounded-sm border font-mono text-[11px] transition-colors border-border hover:border-foreground/30 text-muted-foreground hover:text-foreground flex items-center gap-2 ${
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
                      <span className="text-[9px] uppercase tracking-widest">
                        torture test
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <label className="flex flex-col gap-2">
              <span className={FIELD_LABEL}>Task</span>
              <input
                className={INPUT_CLASS}
                type="text"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Create a new account and reach the verification step."
              />
            </label>

            <div className="flex flex-col gap-2">
              <span className={FIELD_LABEL}>Memory mode</span>
              <div
                className="grid grid-cols-3 gap-1 p-1 rounded-md border border-border bg-background"
                role="radiogroup"
                aria-label="Memory mode"
              >
                {MEMORY_MODES.map((m) => {
                  const on = memoryMode === m.value;
                  return (
                    <button
                      type="button"
                      key={m.value}
                      role="radio"
                      aria-checked={on}
                      onClick={() => setMemoryMode(m.value)}
                      className={`px-2 py-1.5 rounded-sm font-mono text-[11px] text-center leading-tight transition-colors ${
                        on
                          ? "bg-live text-on-live"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {m.label}
                    </button>
                  );
                })}
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {MEMORY_MODES.find((m) => m.value === memoryMode)?.helper}
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <span className={FIELD_LABEL}>
                Specimen roster{" "}
                <span className="text-foreground tabular-nums normal-case tracking-normal">
                  {selected.length}/{catalog.length} armed
                </span>
              </span>
              <div className="grid sm:grid-cols-2 gap-2">
                {catalog.map((p) => {
                  const on = selected.includes(p.id);
                  const badges = perturbationBadges(p);
                  return (
                    <motion.button
                      type="button"
                      key={p.id}
                      whileTap={{ scale: 0.98 }}
                      className={`px-3 py-2.5 rounded-md border text-left transition-colors ${
                        on
                          ? "border-border bg-background"
                          : "border-hairline bg-transparent opacity-60 hover:opacity-100"
                      }`}
                      onClick={() => toggle(p.id)}
                      aria-pressed={on}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium truncate">
                          {p.name}
                        </span>
                        <span
                          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                            on ? "bg-live" : "border border-idle/50"
                          }`}
                          aria-hidden="true"
                        />
                      </span>
                      <span className="block text-xs text-muted-foreground truncate mt-0.5">
                        {p.blurb}
                      </span>
                      <span className="flex flex-wrap gap-x-2 mt-1.5 min-h-3.5">
                        {badges.length ? (
                          badges.map((b) => (
                            <span
                              key={b.kind}
                              title={b.title}
                              className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest"
                            >
                              {b.text}
                            </span>
                          ))
                        ) : (
                          <span
                            className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest"
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
            </div>

            {error && (
              <p className="font-mono text-xs text-fail border border-fail/30 bg-fail/10 rounded-md px-3 py-2.5">
                {error}
              </p>
            )}

            <div className="flex flex-col gap-3">
              <motion.button
                type="submit"
                className="w-full py-3 rounded-md bg-live text-on-live font-mono text-sm font-medium uppercase tracking-widest disabled:opacity-50"
                whileTap={{ scale: 0.99 }}
                disabled={!canLaunch}
              >
                {busy ? "Starting simulation…" : "Run simulation"}
              </motion.button>
              <button
                type="button"
                className="self-center font-mono text-xs text-muted-foreground hover:text-foreground transition-colors uppercase tracking-widest"
                onClick={onOfflineDemo}
              >
                Offline demo →
              </button>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Works on any live URL — public sites, staging, or the bundled
                hostile form. No backend? The offline demo replays a full run
                from local fixtures.
              </p>
            </div>
          </div>
        </motion.form>
      </div>
    </section>
  );
}
