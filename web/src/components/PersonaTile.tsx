import type { PersonaLiveState, Viewport } from "../types";
import { OUTCOME_LABELS } from "../types";
import {
  perceptionFilter,
  perturbationBadges,
  personaColor,
  STATUS,
} from "../theme";

const BASE = import.meta.env.BASE_URL || "/";
const FALLBACK_BG = `${BASE}fixtures/sample_screenshot.png`;

interface Props {
  live: PersonaLiveState;
  index: number;
  coordSpace?: Viewport; // pixel space of x/y coords (default persona viewport)
}

export function PersonaTile({ live, index, coordSpace }: Props) {
  const { persona, status, lastCaption, lastThumb, step, failure, blockedSteps } =
    live;
  const color = personaColor(index);
  const badges = perturbationBadges(persona);
  const space: Viewport =
    coordSpace ?? persona.viewport ?? { width: 1280, height: 800 };

  const dead = status === "abandoned";
  const won = status === "success";
  const running = status === "running";
  const pending = status === "pending";

  const ringColor = won
    ? STATUS.good
    : dead
    ? STATUS.critical
    : running
    ? color
    : "rgba(255,255,255,0.18)";

  const marker = failure?.coords ?? null;
  const markerLeft = marker ? (marker[0] / space.width) * 100 : 0;
  const markerTop = marker ? (marker[1] / space.height) * 100 : 0;

  const bg = lastThumb || FALLBACK_BG;
  const filter = lastThumb ? undefined : perceptionFilter(persona);

  const stateClass = [
    "tile",
    running ? "tile--running" : "",
    won ? "tile--won" : "",
    dead ? "tile--dead" : "",
    pending ? "tile--pending" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={stateClass}
      style={{ ["--ring" as string]: ringColor, ["--accent" as string]: color }}
      aria-label={`${persona.name} — ${
        won ? "completed" : dead ? "abandoned" : running ? "running" : "waiting"
      }`}
    >
      {/* Screenshot / thumbnail layer */}
      <div
        className="tile__screen"
        style={{
          backgroundImage: `url("${bg}")`,
          filter,
        }}
      />
      <div className="tile__scrim" />
      {dead && <div className="tile__fail-veil" />}

      {/* Failure marker */}
      {dead && marker && (
        <div
          className="tile__marker"
          style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
          title={`Died at ${marker[0]}, ${marker[1]}`}
        >
          <span className="tile__marker-ring" />
          <span className="tile__marker-dot" />
          <span className="tile__marker-coords">
            {marker[0]},{marker[1]}
          </span>
        </div>
      )}

      {/* Header: name + status ring + badges */}
      <header className="tile__head">
        <span className="tile__ring" aria-hidden="true">
          {running && <span className="tile__ring-pulse" />}
        </span>
        <div className="tile__id">
          <div className="tile__name">{persona.name}</div>
          {persona.blurb && <div className="tile__blurb">{persona.blurb}</div>}
        </div>
        <div className="tile__badges">
          {blockedSteps > 0 && (
            <span
              className="badge badge--shield"
              title={`${blockedSteps} action${
                blockedSteps === 1 ? "" : "s"
              } blocked by the NemoClaw policy gateway`}
            >
              🛡{blockedSteps}
            </span>
          )}
          {badges.map((b) => (
            <span key={b.kind} className="badge" title={b.label}>
              {b.icon}
            </span>
          ))}
        </div>
      </header>

      {/* Footer: caption or death stamp */}
      <footer className="tile__foot">
        {dead ? (
          <div className="tile__stamp">
            <div className="tile__stamp-title">
              Abandoned · step {failure?.stepsSurvived ?? step}
            </div>
            <div className="tile__stamp-outcome">
              {OUTCOME_LABELS[failure?.outcome ?? "stuck"]}
            </div>
            {failure?.reason && (
              <div className="tile__stamp-reason">“{failure.reason}”</div>
            )}
          </div>
        ) : won ? (
          <div className="tile__caption tile__caption--won">
            <span className="tile__step">step {step}</span>
            ✓ Completed the task
          </div>
        ) : (
          <div className="tile__caption">
            <span className="tile__step">
              {pending ? "—" : `step ${step}`}
            </span>
            {lastCaption}
            {running && <span className="tile__cursor" />}
          </div>
        )}
      </footer>

      {won && <div className="tile__win-glow" />}
    </article>
  );
}
