// Members page: who has a seat on the active project. The owner can invite
// teammates by email and remove non-owners. Invites fail loudly for the cases
// the backend enforces: 402 (seat limit → upgrade), 404 (no such user yet),
// 409 (already a member). Match app tokens; keyboard-accessible.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { ApiError } from "../api2";
import * as billing from "../api_billing";
import type { Member } from "../api_billing";

// A structured invite error so the UI can render an upgrade link on 402.
interface InviteError {
  message: string;
  upgrade: boolean;
}

function RoleBadge({ role }: { role: Member["role"] }) {
  const isOwner = role === "owner";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-mono ${
        isOwner
          ? "border-ok/40 text-ok"
          : "border-border text-muted-foreground"
      }`}
    >
      {isOwner ? "Owner" : "Member"}
    </span>
  );
}

export default function Members() {
  const { activeProject } = useAuth();
  const projectId = activeProject?.id ?? null;

  const [members, setMembers] = useState<Member[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<InviteError | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      setMembers(await billing.listMembers(projectId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load members");
      setMembers(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setMembers(null);
    void load();
  }, [load]);

  async function handleInvite() {
    const addr = email.trim();
    if (!addr || !projectId) return;
    setInviting(true);
    setInviteError(null);
    try {
      await billing.addMember(projectId, addr);
      setEmail("");
      await load();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 402) {
          setInviteError({ message: err.message, upgrade: true });
        } else if (err.status === 404) {
          setInviteError({
            message: "No user with that email — they must sign up first.",
            upgrade: false,
          });
        } else if (err.status === 409) {
          setInviteError({
            message: "That person is already a member.",
            upgrade: false,
          });
        } else {
          setInviteError({ message: err.message, upgrade: false });
        }
      } else {
        setInviteError({ message: "Couldn't send the invite", upgrade: false });
      }
    } finally {
      setInviting(false);
    }
  }

  async function handleRemove(userId: string) {
    if (!projectId) return;
    setRemoving(userId);
    setError(null);
    try {
      await billing.removeMember(projectId, userId);
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't remove the member"
      );
    } finally {
      setRemoving(null);
    }
  }

  if (!activeProject) {
    return (
      <div className="text-sm text-muted-foreground">
        No project selected. Create one from the project switcher to manage
        members.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-lg font-semibold">Members</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Teammates with access to{" "}
          <span className="text-foreground">{activeProject.name}</span>.
        </p>
      </div>

      {/* Invite */}
      <section>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleInvite();
            }}
            placeholder="teammate@company.com"
            aria-label="Invite by email"
            disabled={inviting}
            className="w-full px-3 py-2 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50 disabled:opacity-40 sm:max-w-xs"
          />
          <button
            type="button"
            onClick={() => void handleInvite()}
            disabled={inviting || !email.trim()}
            className="whitespace-nowrap rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {inviting ? "Inviting…" : "Invite"}
          </button>
        </div>
        {inviteError && (
          <p className="mt-2 text-sm text-fail" role="alert">
            {inviteError.message}
            {inviteError.upgrade && (
              <>
                {" "}
                <Link
                  to="/app/billing"
                  className="underline transition-colors hover:text-foreground"
                >
                  Upgrade your plan
                </Link>
                .
              </>
            )}
          </p>
        )}
      </section>

      {/* List */}
      <section>
        {loading && members === null ? (
          <p className="text-sm text-muted-foreground">Loading members…</p>
        ) : error ? (
          <div className="flex items-center gap-3" role="alert">
            <p className="text-sm text-fail">{error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="text-xs text-muted-foreground underline transition-colors hover:text-foreground"
            >
              Retry
            </button>
          </div>
        ) : members && members.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No members yet. Invite a teammate above.
          </p>
        ) : members ? (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Email</th>
                  <th className="px-4 py-2.5 font-medium">Role</th>
                  <th className="px-4 py-2.5 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => {
                  const isOwner = m.role === "owner";
                  return (
                    <tr
                      key={m.user_id}
                      className="border-b border-border last:border-0"
                    >
                      <td className="px-4 py-2.5 text-foreground">{m.email}</td>
                      <td className="px-4 py-2.5">
                        <RoleBadge role={m.role} />
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {!isOwner && (
                          <button
                            type="button"
                            onClick={() => void handleRemove(m.user_id)}
                            disabled={removing === m.user_id}
                            className="text-xs text-muted-foreground transition-colors hover:text-fail disabled:opacity-40"
                          >
                            {removing === m.user_id ? "Removing…" : "Remove"}
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
