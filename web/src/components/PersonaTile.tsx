import type { PerturbationKind } from "../types";
import type { PersonaLive } from "../useRunStream";

/** Little badges for each degraded channel (per work package). */
const PERTURBATION_BADGES: Record<PerturbationKind, { icon: string; label: string }> = {
  blur: { icon: "\u{1F441}️", label: "blur (low vision)" },
  downscale: { icon: "\u{1F50D}", label: "downscale (low acuity)" },
  cvd: { icon: "\u{1F3A8}", label: "color-vision deficiency" },
  tremor: { icon: "✋", label: "hand tremor" },
  small_viewport: { icon: "\u{1F4F1}", label: "small viewport" },
  impatience: { icon: "⏱️", label: "impatience (tight budget)" },
  low_literacy: { icon: "\u{1F524}", label: "literal reading" },
};

const OUTCOME_STAMP: Record<string, string> = {
  step_budget: "ran out of steps",
  time_budget: "ran out of time",
  stuck: "gave up",
  error: "session crashed",
};

/** Map viewport-pixel coords to a percentage position inside the tile screen. */
function toPercent(
  coords: [number, number],
  viewport: { width: number; height: number },
): { left: string; top: string } {
  const x = Math.min(Math.max(coords[0] / viewport.width, 0), 1);
  const y = Math.min(Math.max(coords[1] / viewport.height, 0), 1);
  return { left: `${(x * 100).toFixed(2)}%`, top: `${(y * 100).toFixed(2)}%` };
}

export default function PersonaTile({ live }: { live: PersonaLive }) {
  const { persona, status, lastCaption, lastThumb, step, lastXY, failure } = live;
  const viewport = persona.viewport ?? { width: 1280, height: 800 };
  const dead = status === "dead" || status === "error";
  const perturbations = persona.active_perturbations ?? [];

  return (
    <article
      className={`tile tile--${status}`}
      aria-label={`${persona.name} — ${status}`}
    >
      <div className="tile__screen">
        {lastThumb ? (
          <img
            className="tile__frame"
            src={lastThumb}
            alt={`Latest frame for ${persona.name}`}
          />
        ) : (
          !dead && (
            <div className="tile__nosignal" aria-hidden="true">
              <span className="glyph">{"\u{1F47B}"}</span>
              <span>
                {status === "pending"
                  ? "summoning"
                  : status === "success"
                    ? "survived"
                    : "live session"}
              </span>
            </div>
          )
        )}
        <div className="tile__scan" aria-hidden="true" />
        <div className="tile__tint" aria-hidden="true" />

        {/* transient ping at the last action's coords while running */}
        {status === "running" && lastXY && (
          <span
            key={`${step}-${lastXY[0]}-${lastXY[1]}`}
            className="tile__ping"
            style={toPercent(lastXY, viewport)}
            aria-hidden="true"
          />
        )}

        {/* the death pixel — crosshair frozen where the persona abandoned */}
        {dead && failure?.coords && (
          <span
            className="tile__cross"
            style={toPercent(failure.coords, viewport)}
            title={`died at (${failure.coords[0]}, ${failure.coords[1]})`}
          >
            <span className="ringmark" aria-hidden="true" />
          </span>
        )}

        {dead && failure ? (
          <div className="tile__epitaph">
            <span className="stamp">
              {"†"} {OUTCOME_STAMP[failure.outcome] ?? "abandoned"} at step{" "}
              {failure.stepsSurvived}
            </span>
            {failure.reason && <span className="reason">{failure.reason}</span>}
          </div>
        ) : (
          <div className="tile__caption">
            {status === "success" ? "task complete" : lastCaption}
          </div>
        )}
      </div>

      <div className="tile__meta">
        <span className={`ring ring--${status}`} role="img" aria-label={status} />
        <span className="tile__name" title={persona.blurb || persona.name}>
          {persona.name}
        </span>
        <span className="tile__badges">
          {perturbations.map((p) => (
            <span
              key={p}
              className="badge"
              title={PERTURBATION_BADGES[p]?.label ?? p}
              role="img"
              aria-label={PERTURBATION_BADGES[p]?.label ?? p}
            >
              {PERTURBATION_BADGES[p]?.icon ?? "?"}
            </span>
          ))}
        </span>
        <span className="tile__spacer" />
        <span className="tile__step">
          {status === "pending" ? "—" : `step ${step}`}
        </span>
      </div>
    </article>
  );
}
