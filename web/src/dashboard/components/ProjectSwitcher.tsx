// Project selector for the dashboard chrome. A native <select> over the user's
// projects bound to the auth context's activeProject, plus a "+ New project"
// action that creates a project and refreshes the list. Handles the
// zero-projects case (a customer whose signup didn't seed a project yet).

import { useState } from "react";
import { useAuth } from "../auth";
import * as api2 from "../api2";
import { ApiError } from "../api2";

const NEW_PROJECT = "__new__";

export function ProjectSwitcher() {
  const { projects, activeProject, setActiveProject, refreshProjects } =
    useAuth();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const project = await api2.createProject(trimmed);
      await refreshProjects();
      setActiveProject(project.id);
      setName("");
      setCreating(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create project");
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    setCreating(false);
    setName("");
    setError(null);
  }

  if (creating) {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <input
            autoFocus
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreate();
              if (e.key === "Escape") cancel();
            }}
            placeholder="Project name"
            aria-label="New project name"
            disabled={busy}
            className="w-40 px-2.5 py-1.5 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50 disabled:opacity-40"
          />
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={busy || !name.trim()}
            className="px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {busy ? "Adding…" : "Add"}
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="px-2 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-hover transition-colors disabled:opacity-40"
          >
            Cancel
          </button>
        </div>
        {error && <p className="text-xs text-fail">{error}</p>}
      </div>
    );
  }

  // Zero-projects fallback: no dropdown to show, just the create affordance.
  if (projects.length === 0) {
    return (
      <button
        type="button"
        onClick={() => setCreating(true)}
        className="px-2.5 py-1.5 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-hover transition-colors"
      >
        + New project
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <label className="sr-only" htmlFor="project-switcher">
        Active project
      </label>
      <select
        id="project-switcher"
        value={activeProject?.id ?? ""}
        onChange={(e) => {
          if (e.target.value === NEW_PROJECT) {
            setCreating(true);
            return;
          }
          setActiveProject(e.target.value);
        }}
        className="max-w-[12rem] px-2.5 py-1.5 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors cursor-pointer"
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
        <option value={NEW_PROJECT}>+ New project…</option>
      </select>
    </div>
  );
}
