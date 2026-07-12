import type { RunState } from "../useRunStream";
import PersonaTile from "./PersonaTile";

export default function PersonaGrid({ state }: { state: RunState }) {
  const tiles = state.order
    .map((id) => state.personas[id])
    .filter((t) => t !== undefined);
  const total = tiles.length;
  const survived = tiles.filter((t) => t.status === "success").length;
  const dead = tiles.filter((t) => t.status === "dead").length;
  const finished = tiles.filter(
    (t) => t.status === "success" || t.status === "dead" || t.status === "error",
  ).length;
  const progress = total === 0 ? 0 : (finished / total) * 100;

  return (
    <div>
      <div className="runbar">
        <div>
          <h2 className="runbar__task">{state.task || "…"}</h2>
          <div className="runbar__target">{state.targetUrl}</div>
        </div>
        <div className="runbar__spacer" />
        <div style={{ textAlign: "right" }}>
          <div className="survived-counter" aria-live="polite">
            {survived}
            <span className="of">/{total}</span>
            <span className="label">survived</span>
          </div>
          {dead > 0 && (
            <div className="deadcount" aria-live="polite">
              {"†"} {dead} abandoned
            </div>
          )}
        </div>
      </div>

      <div
        className="progress"
        role="progressbar"
        aria-valuenow={finished}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label="personas finished"
      >
        <div className="progress__fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="grid">
        {tiles.map((t) => (
          <PersonaTile key={t.persona.id} live={t} />
        ))}
      </div>
    </div>
  );
}
