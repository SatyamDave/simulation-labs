// IcpPicker — chooses the `icp.personas` value for a sim.yml. Either the string
// "auto" (the full bundled roster) or an explicit list of persona ids. Ids come
// from personaCatalog and match ghostpanel.cli.config.IcpCfg.personas EXACTLY.
// Controlled: `value` is the source of truth; we remember the last manual
// selection so toggling "auto" off restores it.

import { useRef } from "react";
import { PERSONA_CATALOG } from "../../personaCatalog";

type IcpValue = string[] | "auto";

interface Props {
  value: IcpValue;
  onChange: (value: IcpValue) => void;
}

const ALL_IDS = PERSONA_CATALOG.map((p) => p.id);

export function IcpPicker({ value, onChange }: Props) {
  const isAuto = value === "auto";
  const selected = isAuto ? [] : value;

  // Remember the last explicit list so flipping "auto" back off restores it.
  const lastManual = useRef<string[]>(ALL_IDS);
  if (!isAuto) lastManual.current = value;

  function setAuto(on: boolean) {
    onChange(on ? "auto" : lastManual.current.length ? lastManual.current : ALL_IDS);
  }

  function toggle(id: string) {
    if (isAuto) return;
    onChange(
      selected.includes(id)
        ? selected.filter((x) => x !== id)
        : [...selected, id]
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input
          type="checkbox"
          className="h-4 w-4 accent-primary"
          checked={isAuto}
          onChange={(e) => setAuto(e.target.checked)}
        />
        <span>auto — send the full bundled roster</span>
      </label>

      <div
        className={`grid gap-2 sm:grid-cols-2 ${
          isAuto ? "opacity-40 pointer-events-none" : ""
        }`}
        aria-disabled={isAuto}
      >
        {PERSONA_CATALOG.map((p) => {
          const on = !isAuto && selected.includes(p.id);
          return (
            <button
              type="button"
              key={p.id}
              className={`px-3 py-2.5 rounded-lg border text-left transition-colors ${
                on ? "border-foreground" : "border-border hover:bg-hover"
              }`}
              onClick={() => toggle(p.id)}
              aria-pressed={on}
              disabled={isAuto}
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
                {p.blurb || p.id}
              </span>
            </button>
          );
        })}
      </div>

      {!isAuto && (
        <p className="text-xs text-muted-foreground">
          {selected.length} persona{selected.length === 1 ? "" : "s"} selected
          {selected.length === 0 && " — the CLI falls back to the full roster"}.
        </p>
      )}
    </div>
  );
}
