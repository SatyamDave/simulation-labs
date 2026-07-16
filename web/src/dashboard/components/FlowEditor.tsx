// FlowEditor — controlled editor for the `flows:` list in a sim.yml. Each flow is
// one behavioral test: name + url + task + a fail_under bar that is either
// "last-passing" (regress-vs-baseline) or an absolute completion number 0..1.
// Field names mirror ghostpanel.cli.config.Flow EXACTLY. Purely client-side —
// the parent (Flows page) turns these into copyable YAML.

// FailUnder mirrors config.py: an absolute completion bar (0..1) or the string
// "last-passing" (block the merge if worse than the last green run).
export type FailUnder = number | "last-passing";

export interface FlowDraft {
  name: string;
  url: string;
  task: string;
  fail_under: FailUnder;
}

export function newFlow(): FlowDraft {
  return {
    name: "signup",
    url: "https://staging.example.com/signup",
    task: "Create an account with a work email and reach the dashboard",
    fail_under: "last-passing",
  };
}

interface Props {
  flows: FlowDraft[];
  onChange: (flows: FlowDraft[]) => void;
}

const FIELD =
  "w-full px-3 py-2 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50";
const LABEL = "text-xs text-muted-foreground";

export function FlowEditor({ flows, onChange }: Props) {
  function patch(index: number, next: Partial<FlowDraft>) {
    onChange(flows.map((f, i) => (i === index ? { ...f, ...next } : f)));
  }

  function remove(index: number) {
    onChange(flows.filter((_, i) => i !== index));
  }

  function add() {
    onChange([...flows, newFlow()]);
  }

  return (
    <div className="flex flex-col gap-4">
      {flows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No flows yet. Add one to describe a task the swarm should attempt.
        </p>
      )}

      {flows.map((flow, i) => {
        const isAbsolute = typeof flow.fail_under === "number";
        return (
          <fieldset
            key={i}
            className="flex flex-col gap-4 rounded-xl border border-border p-4"
          >
            <legend className="sr-only">Flow {i + 1}</legend>

            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">
                Flow {i + 1}
              </span>
              <button
                type="button"
                onClick={() => remove(i)}
                className="text-xs text-muted-foreground hover:text-fail transition-colors"
              >
                Remove
              </button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-2">
                <span className={LABEL}>Name</span>
                <input
                  className={FIELD}
                  type="text"
                  value={flow.name}
                  onChange={(e) => patch(i, { name: e.target.value })}
                  placeholder="signup"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className={LABEL}>URL</span>
                <input
                  className={`${FIELD} font-mono`}
                  type="text"
                  value={flow.url}
                  onChange={(e) => patch(i, { url: e.target.value })}
                  placeholder="https://your-site.com/signup"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            </div>

            <label className="flex flex-col gap-2">
              <span className={LABEL}>Task</span>
              <input
                className={FIELD}
                type="text"
                value={flow.task}
                onChange={(e) => patch(i, { task: e.target.value })}
                placeholder="Create an account and reach the dashboard"
              />
            </label>

            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-3">
              <label className="flex flex-1 flex-col gap-2">
                <span className={LABEL}>Fail under</span>
                <select
                  className={FIELD}
                  value={isAbsolute ? "absolute" : "last-passing"}
                  onChange={(e) =>
                    patch(i, {
                      fail_under:
                        e.target.value === "absolute"
                          ? typeof flow.fail_under === "number"
                            ? flow.fail_under
                            : 0.8
                          : "last-passing",
                    })
                  }
                >
                  <option value="last-passing">
                    last-passing (regress vs. baseline)
                  </option>
                  <option value="absolute">absolute bar (0..1)</option>
                </select>
              </label>

              {isAbsolute && (
                <label className="flex flex-col gap-2 sm:w-32">
                  <span className={LABEL}>Bar (0..1)</span>
                  <input
                    className={FIELD}
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={flow.fail_under as number}
                    onChange={(e) => {
                      const n = parseFloat(e.target.value);
                      patch(i, {
                        fail_under: Number.isNaN(n)
                          ? 0
                          : Math.min(1, Math.max(0, n)),
                      });
                    }}
                    aria-label={`Absolute completion bar for flow ${i + 1}`}
                  />
                </label>
              )}
            </div>
          </fieldset>
        );
      })}

      <button
        type="button"
        onClick={add}
        className="self-start px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:bg-hover hover:text-foreground transition-colors"
      >
        + Add flow
      </button>
    </div>
  );
}
