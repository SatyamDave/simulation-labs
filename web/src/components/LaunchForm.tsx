import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { listPersonas } from "../api";
import { PERSONA_CATALOG, type CatalogEntry } from "../personaCatalog";
import { perturbationBadges } from "../theme";
import { FlatlineGlyph } from "./VitalLine";

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
// Selecting one fills the URL and a matching task.
const EXAMPLES: { label: string; url: string; task: string }[] = [
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
  },
];

const FIELD_LABEL = "text-xs text-muted-foreground";

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
    <section className="px-6 pt-20 pb-24 md:pt-28">
      <motion.div
        className="mx-auto max-w-xl"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
      >
        <FlatlineGlyph className="text-foreground mb-8" />

        <h1 className="text-4xl font-semibold tracking-tight">
          See where users give up.
        </h1>
        <p className="text-muted-foreground mt-3 mb-12 leading-relaxed">
          Impaired synthetic users attempt a real task on your site and record
          the exact pixel where each one abandons.
        </p>

        <form
          className="flex flex-col gap-7"
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
          <div className="flex flex-col gap-2">
            <input
              className="w-full px-4 py-3 font-mono text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50"
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://your-site.com/signup"
              aria-label="Target URL"
              autoComplete="off"
              spellCheck={false}
            />
            <div className="flex flex-wrap gap-x-4 gap-y-1 px-1">
              <span className="text-xs text-muted-foreground/60">Try</span>
              {EXAMPLES.map((ex) => (
                <button
                  type="button"
                  key={ex.url}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => {
                    setUrl(ex.url);
                    setTask(ex.task);
                  }}
                  title={ex.url}
                >
                  {ex.label}
                </button>
              ))}
            </div>
          </div>

          <label className="flex flex-col gap-2">
            <span className={FIELD_LABEL}>Task</span>
            <input
              className="w-full px-4 py-2.5 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50"
              type="text"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Create a new account and reach the verification step."
            />
          </label>

          <div className="flex flex-col gap-2">
            <span className={FIELD_LABEL}>
              Personas · {selected.length} of {catalog.length}
            </span>
            <div className="grid sm:grid-cols-2 gap-2">
              {catalog.map((p) => {
                const on = selected.includes(p.id);
                const badges = perturbationBadges(p);
                return (
                  <button
                    type="button"
                    key={p.id}
                    className={`px-3 py-2.5 rounded-lg border text-left transition-colors ${
                      on
                        ? "border-foreground"
                        : "border-border hover:bg-hover"
                    }`}
                    onClick={() => toggle(p.id)}
                    aria-pressed={on}
                    title={p.blurb || p.name}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className={`text-sm font-medium truncate ${
                          on ? "" : "text-muted-foreground"
                        }`}
                      >
                        {p.name}
                      </span>
                      {on && (
                        <svg
                          className="w-3.5 h-3.5 ml-auto shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      )}
                    </span>
                    <span className="block font-mono text-[10px] text-muted-foreground truncate mt-1">
                      {badges.length
                        ? badges.map((b) => b.text).join(" · ")
                        : "baseline"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {error && <p className="text-sm text-fail">{error}</p>}

          <div className="flex flex-col gap-4">
            <button
              type="submit"
              className="w-full py-3 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
              disabled={!canLaunch}
            >
              {busy ? "Starting…" : "Run simulation"}
            </button>
            <button
              type="button"
              className="self-center text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={onOfflineDemo}
            >
              or watch the offline demo →
            </button>
          </div>
        </form>
      </motion.div>
    </section>
  );
}
