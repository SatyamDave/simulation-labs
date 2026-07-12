import type { LiveRunState, Viewport } from "../types";
import { tallies } from "../runReducer";
import { PersonaTile } from "./PersonaTile";

interface Props {
  state: LiveRunState;
  coordSpace?: Viewport;
  onSeeReport?: () => void;
  reportReady?: boolean;
}

export function PersonaGrid({
  state,
  coordSpace,
  onSeeReport,
  reportReady,
}: Props) {
  const t = tallies(state);
  const progress = t.total ? Math.round((t.done / t.total) * 100) : 0;

  return (
    <section className="grid-wrap">
      <div className="grid-head">
        <div className="grid-head__meta">
          <div className="grid-head__task">
            <span className="grid-head__label">TASK</span>
            <span className="grid-head__task-text">{state.task || "—"}</span>
          </div>
          <div className="grid-head__url">{state.targetUrl}</div>
        </div>

        <div className="grid-head__stats">
          <div className="stat stat--alive">
            <div className="stat__num">{t.survived}</div>
            <div className="stat__lbl">survived</div>
          </div>
          <div className="stat stat--dead">
            <div className="stat__num">{t.dead}</div>
            <div className="stat__lbl">abandoned</div>
          </div>
          <div className="stat">
            <div className="stat__num">
              {t.running > 0 ? t.running : t.done === t.total ? "✓" : "…"}
            </div>
            <div className="stat__lbl">
              {t.running > 0 ? "still trying" : "all done"}
            </div>
          </div>
          <div className="stat stat--total">
            <div className="stat__num">
              {t.done}/{t.total}
            </div>
            <div className="stat__lbl">finished</div>
          </div>
        </div>
      </div>

      <div className="progress">
        <div className="progress__bar" style={{ width: `${progress}%` }} />
      </div>

      <div className="grid">
        {state.order.map((id, i) => {
          const live = state.personas[id];
          if (!live) return null;
          return (
            <PersonaTile
              key={id}
              live={live}
              index={i}
              coordSpace={coordSpace}
            />
          );
        })}
      </div>

      {reportReady && onSeeReport && (
        <div className="grid-cta">
          <button className="btn btn--primary btn--big" onClick={onSeeReport}>
            Read the autopsy →
          </button>
        </div>
      )}
    </section>
  );
}
