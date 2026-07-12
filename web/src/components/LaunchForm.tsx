import { useState } from "react";
import { PERSONA_CATALOG } from "../personaCatalog";
import { perturbationBadges } from "../theme";

export interface LaunchValues {
  target_url: string;
  task: string;
  persona_ids: string[];
}

interface Props {
  onLaunch: (v: LaunchValues) => void;
  onOfflineDemo: () => void;
  onIndex?: () => void;
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

export function LaunchForm({ onLaunch, onOfflineDemo, onIndex, busy, error }: Props) {
  const [url, setUrl] = useState("https://github.com/signup");
  const [task, setTask] = useState(
    "Create a new account and reach the verification step."
  );
  const [selected, setSelected] = useState<string[]>(
    PERSONA_CATALOG.map((p) => p.id)
  );

  function toggle(id: string) {
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id]
    );
  }

  const canLaunch = url.trim() && task.trim() && selected.length > 0 && !busy;

  return (
    <div className="launch">
      <div className="launch__hero">
        <span className="launch__eyebrow">
          <span className="launch__eyebrow-dot" /> Simulation Labs
        </span>
        <h1 className="launch__title">
          See who fails your site — <span>before your users do.</span>
        </h1>
        <p className="launch__tag">
          A swarm of computer-use agents (H&nbsp;Company Holo) with{" "}
          <em>mechanically degraded</em> perception and actuation attempts real
          tasks on any live site — and reports the exact point where real users
          give up.
        </p>
      </div>

      <form
        className="launch__form"
        onSubmit={(e) => {
          e.preventDefault();
          if (canLaunch)
            onLaunch({ target_url: url.trim(), task: task.trim(), persona_ids: selected });
        }}
      >
        <div className="field">
          <span className="field__label">Target URL</span>
          <input
            className="field__input"
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/signup"
            autoComplete="off"
            spellCheck={false}
          />
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button
                type="button"
                key={ex.url}
                className={`example-chip ${
                  ex.torture ? "example-chip--torture" : ""
                }`}
                onClick={() => {
                  setUrl(ex.url);
                  setTask(ex.task);
                }}
                title={ex.url}
              >
                {ex.label}
                {ex.torture && (
                  <span className="example-chip__tag">torture test</span>
                )}
              </button>
            ))}
          </div>
        </div>

        <label className="field">
          <span className="field__label">Task</span>
          <input
            className="field__input"
            type="text"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Create a new account and reach the verification step."
          />
        </label>

        <div className="field">
          <span className="field__label">
            The panel{" "}
            <span className="field__hint">
              {selected.length}/{PERSONA_CATALOG.length} selected
            </span>
          </span>
          <div className="persona-picker">
            {PERSONA_CATALOG.map((p) => {
              const on = selected.includes(p.id);
              const badges = perturbationBadges(p);
              return (
                <button
                  type="button"
                  key={p.id}
                  className={`persona-chip ${on ? "persona-chip--on" : ""}`}
                  onClick={() => toggle(p.id)}
                  aria-pressed={on}
                >
                  <span className="persona-chip__check">{on ? "✓" : "+"}</span>
                  <span className="persona-chip__body">
                    <span className="persona-chip__name">{p.name}</span>
                    <span className="persona-chip__blurb">{p.blurb}</span>
                  </span>
                  <span className="persona-chip__badges">
                    {badges.length
                      ? badges.map((b) => (
                          <span key={b.kind} title={b.label}>
                            {b.icon}
                          </span>
                        ))
                      : <span className="persona-chip__clean" title="No perturbation — baseline">◆</span>}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="launch__fidelity">
            <span><b>Mechanical fidelity, not roleplay:</b></span>
            <span>blur = low vision</span>
            <span>coordinate noise = tremor</span>
            <span>tight budgets = impatience</span>
          </div>
        </div>

        {error && <div className="launch__error">⚠ {error}</div>}

        <div className="launch__actions">
          <button
            type="submit"
            className="btn btn--primary btn--big"
            disabled={!canLaunch}
          >
            {busy ? "Starting simulation…" : "Run simulation"}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onOfflineDemo}
          >
            ▶ Offline demo
          </button>
          {onIndex && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onIndex}
              title="Every run on this server, worst sites first"
            >
              📊 Index
            </button>
          )}
        </div>
        <p className="launch__note">
          Works on any live URL — public sites, staging, or the bundled hostile
          form. No backend? The <strong>Offline demo</strong> replays a full run
          from local fixtures — completely self-contained.
        </p>
      </form>
    </div>
  );
}
