// Settings page: the active project's identity (name + tier) and its API keys.
// Keys are created against the /v2 API; the plaintext secret is shown ONCE at
// creation (the server only stores a hash), so we surface it in a copy box with
// a loud "you won't see this again" warning and never render it after refresh.

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import * as api2 from "../api2";
import { ApiError } from "../api2";
import type { ApiKeyRow, CreatedApiKey, Tier } from "../types2";

const TIER_LABEL: Record<Tier, string> = {
  free: "Free",
  team: "Team",
  audit: "Audit",
};

function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span className="px-2 py-0.5 rounded-full border border-border text-xs font-mono text-muted-foreground">
      {TIER_LABEL[tier] ?? tier}
    </span>
  );
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function CreatedKeyBox({
  created,
  onDismiss,
}: {
  created: CreatedApiKey;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(created.plaintext);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable — the value is selectable in the box */
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-live/40 bg-hover p-4">
      <p className="text-sm font-bold text-live">
        Copy this key now — you won&apos;t see it again.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        This is the only time the full secret for{" "}
        <span className="font-mono">{created.key.name}</span> is shown. We store
        only a hash.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <code className="flex-1 min-w-0 truncate rounded-lg border border-border bg-background px-3 py-2 font-mono text-sm">
          {created.plaintext}
        </code>
        <button
          type="button"
          onClick={() => void copy()}
          className="px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity whitespace-nowrap"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="mt-3 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        I&apos;ve saved it — dismiss
      </button>
    </div>
  );
}

export default function Settings() {
  const { activeProject } = useAuth();
  const projectId = activeProject?.id ?? null;

  const [keys, setKeys] = useState<ApiKeyRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [newKeyName, setNewKeyName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const rows = await api2.listKeys(projectId);
      setKeys(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load API keys");
      setKeys(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setKeys(null);
    setCreated(null);
    void load();
  }, [load]);

  async function handleCreate() {
    const name = newKeyName.trim();
    if (!name || !projectId) return;
    setCreating(true);
    setCreateError(null);
    try {
      const result = await api2.createKey(projectId, name);
      setCreated(result);
      setNewKeyName("");
      await load();
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : "Couldn't create the key"
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(keyId: string) {
    if (!projectId) return;
    setRevoking(keyId);
    setError(null);
    try {
      await api2.revokeKey(projectId, keyId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't revoke the key");
    } finally {
      setRevoking(null);
    }
  }

  if (!activeProject) {
    return (
      <div className="text-sm text-muted-foreground">
        No project selected. Create one from the project switcher to manage
        settings.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <div className="mt-2 flex items-center gap-2.5">
          <span className="text-sm text-foreground">{activeProject.name}</span>
          <TierBadge tier={activeProject.tier} />
        </div>
      </div>

      <section>
        <div className="mb-4">
          <h2 className="text-base font-semibold">API keys</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Used by the <span className="font-mono">sim</span> CLI in your CI to
            authenticate runs against this project.
          </p>
        </div>

        {created && (
          <CreatedKeyBox created={created} onDismiss={() => setCreated(null)} />
        )}

        {/* Create */}
        <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start">
          <input
            type="text"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreate();
            }}
            placeholder="Key name (e.g. ci-github-actions)"
            aria-label="New key name"
            disabled={creating}
            className="w-full sm:max-w-xs px-3 py-2 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50 disabled:opacity-40"
          />
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={creating || !newKeyName.trim()}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 whitespace-nowrap"
          >
            {creating ? "Creating…" : "Create key"}
          </button>
        </div>
        {createError && (
          <p className="-mt-4 mb-6 text-sm text-fail">{createError}</p>
        )}

        {/* List */}
        {loading && keys === null ? (
          <p className="text-sm text-muted-foreground">Loading keys…</p>
        ) : error ? (
          <div className="flex items-center gap-3">
            <p className="text-sm text-fail">{error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="text-xs text-muted-foreground hover:text-foreground underline transition-colors"
            >
              Retry
            </button>
          </div>
        ) : keys && keys.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No API keys yet. Create one above to connect your CI.
          </p>
        ) : keys ? (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Name</th>
                  <th className="px-4 py-2.5 font-medium">Prefix</th>
                  <th className="px-4 py-2.5 font-medium">Created</th>
                  <th className="px-4 py-2.5 font-medium">Last used</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => {
                  const revoked = Boolean(k.revoked_at);
                  return (
                    <tr
                      key={k.id}
                      className="border-b border-border last:border-0"
                    >
                      <td className="px-4 py-2.5">{k.name}</td>
                      <td className="px-4 py-2.5 font-mono text-muted-foreground">
                        {k.prefix}…
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {fmtDate(k.created_at)}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {fmtDate(k.last_used_at)}
                      </td>
                      <td className="px-4 py-2.5">
                        {revoked ? (
                          <span className="text-fail">
                            Revoked {fmtDate(k.revoked_at)}
                          </span>
                        ) : (
                          <span className="text-ok">Active</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {!revoked && (
                          <button
                            type="button"
                            onClick={() => void handleRevoke(k.id)}
                            disabled={revoking === k.id}
                            className="text-xs text-muted-foreground hover:text-fail transition-colors disabled:opacity-40"
                          >
                            {revoking === k.id ? "Revoking…" : "Revoke"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
