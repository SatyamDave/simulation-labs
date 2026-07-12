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
  busy?: boolean;
  error?: string | null;
}

export function LaunchForm({ onLaunch, onOfflineDemo, busy, error }: Props) {
  const [url, setUrl] = useState("https://example.com/signup");
  const [task, setTask] = useState("Create an account and start the free trial.");
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
        <div className="launch__ghost" aria-hidden="true">
          👻
        </div>
        <h1 className="launch__title">
          Ghost<span>panel</span>
        </h1>
        <p className="launch__tag">
          Synthetic users that <em>do</em>, not <em>say</em>. Point the swarm at
          your site and watch who survives — and who freezes red at the pixel
          they give up.
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
        <label className="field">
          <span className="field__label">Target URL</span>
          <input
            className="field__input"
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://your-site.com/signup"
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <label className="field">
          <span className="field__label">Task</span>
          <input
            className="field__input"
            type="text"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Create an account and start the free trial."
          />
        </label>

        <div className="field">
          <span className="field__label">
            The swarm{" "}
            <span className="field__hint">
              {selected.length}/{PERSONA_CATALOG.length} summoned
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
                      : <span className="persona-chip__clean" title="No impairment">✦</span>}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {error && <div className="launch__error">⚠ {error}</div>}

        <div className="launch__actions">
          <button
            type="submit"
            className="btn btn--primary btn--big"
            disabled={!canLaunch}
          >
            {busy ? "Summoning…" : "Unleash the swarm 👻"}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onOfflineDemo}
          >
            ▶ Offline demo
          </button>
        </div>
        <p className="launch__note">
          No backend? The <strong>Offline demo</strong> replays a canned run from
          local fixtures — fully self-contained.
        </p>
      </form>
    </div>
  );
}
