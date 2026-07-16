// Billing page: the active project's plan, entitlements, and usage. Free plans
// can upgrade to Team (Stripe Checkout); subscribed projects manage billing via
// the Stripe customer portal. When Stripe isn't configured on the instance we
// hide the upgrade path and say so. Quota (402) errors surface inline.

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { ApiError } from "../api2";
import * as billing from "../api_billing";
import type { BillingInfo } from "../api_billing";

function pct(used: number, quota: number): number {
  if (quota < 0) return 0; // unlimited — no bar fill
  if (quota === 0) return 100;
  return Math.min(100, Math.round((used / quota) * 100));
}

function fmtQuota(quota: number): string {
  return quota < 0 ? "unlimited" : String(quota);
}

function UsageMeter({
  label,
  used,
  quota,
}: {
  label: string;
  used: number;
  quota: number;
}) {
  const unlimited = quota < 0;
  const fill = pct(used, quota);
  const near = !unlimited && fill >= 80;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-foreground">{label}</span>
        <span className="font-mono text-muted-foreground">
          {used} / {fmtQuota(quota)}
        </span>
      </div>
      <div
        className="mt-2 h-2 w-full overflow-hidden rounded-full bg-hover"
        role="progressbar"
        aria-valuenow={unlimited ? undefined : used}
        aria-valuemin={0}
        aria-valuemax={unlimited ? undefined : quota}
        aria-label={`${label}: ${used} of ${fmtQuota(quota)}`}
      >
        <div
          className={`h-full rounded-full transition-all ${
            near ? "bg-fail" : "bg-ok"
          }`}
          style={{ width: unlimited ? "8%" : `${fill}%` }}
        />
      </div>
    </div>
  );
}

export default function Billing() {
  const { activeProject } = useAuth();
  const projectId = activeProject?.id ?? null;

  const [info, setInfo] = useState<BillingInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      setInfo(await billing.getBilling(projectId));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't load billing details"
      );
      setInfo(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setInfo(null);
    void load();
  }, [load]);

  async function handleUpgrade() {
    if (!projectId) return;
    setActing(true);
    setActionError(null);
    try {
      const { url } = await billing.startCheckout(projectId, {
        success_url: window.location.href,
        cancel_url: window.location.href,
      });
      window.location.assign(url);
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Couldn't start checkout"
      );
      setActing(false);
    }
  }

  async function handlePortal() {
    if (!projectId) return;
    setActing(true);
    setActionError(null);
    try {
      const { url } = await billing.openPortal(projectId, {
        return_url: window.location.href,
      });
      window.location.assign(url);
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Couldn't open the billing portal"
      );
      setActing(false);
    }
  }

  if (!activeProject) {
    return (
      <div className="text-sm text-muted-foreground">
        No project selected. Create one from the project switcher to manage
        billing.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-lg font-semibold">Billing</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Plan, usage, and payment for{" "}
          <span className="text-foreground">{activeProject.name}</span>.
        </p>
      </div>

      {loading && info === null ? (
        <p className="text-sm text-muted-foreground">Loading billing…</p>
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
      ) : info ? (
        <>
          {/* Plan */}
          <section className="rounded-xl border border-border bg-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Current plan
                </p>
                <div className="mt-1 flex items-baseline gap-2.5">
                  <span className="text-xl font-semibold text-foreground">
                    {info.entitlements.label}
                  </span>
                  <span className="font-mono text-sm text-muted-foreground">
                    {info.entitlements.price_display}
                  </span>
                </div>
              </div>

              {info.stripe_configured ? (
                info.tier === "free" ? (
                  <button
                    type="button"
                    onClick={() => void handleUpgrade()}
                    disabled={acting}
                    className="whitespace-nowrap rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
                  >
                    {acting ? "Redirecting…" : "Upgrade to Team"}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void handlePortal()}
                    disabled={acting}
                    className="whitespace-nowrap rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-hover disabled:opacity-40"
                  >
                    {acting ? "Opening…" : "Manage billing"}
                  </button>
                )
              ) : null}
            </div>

            {!info.stripe_configured && (
              <p className="mt-4 text-xs text-muted-foreground">
                Billing isn&apos;t enabled on this instance.
              </p>
            )}
            {actionError && (
              <p className="mt-4 text-sm text-fail" role="alert">
                {actionError}
              </p>
            )}
          </section>

          {/* Usage */}
          <section>
            <h2 className="mb-4 text-base font-semibold">Usage</h2>
            <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5">
              <UsageMeter
                label="Runs this period"
                used={info.usage.runs_this_period}
                quota={info.entitlements.max_runs_per_month}
              />
              <UsageMeter
                label="Seats"
                used={info.usage.seats}
                quota={info.entitlements.max_seats}
              />
            </div>
          </section>

          {/* Entitlements */}
          <section>
            <h2 className="mb-4 text-base font-semibold">What&apos;s included</h2>
            <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-3">
              <div className="bg-card p-4">
                <dt className="text-xs text-muted-foreground">Flows</dt>
                <dd className="mt-1 font-mono text-sm text-foreground">
                  {fmtQuota(info.entitlements.max_flows)}
                </dd>
              </div>
              <div className="bg-card p-4">
                <dt className="text-xs text-muted-foreground">Runs / month</dt>
                <dd className="mt-1 font-mono text-sm text-foreground">
                  {fmtQuota(info.entitlements.max_runs_per_month)}
                </dd>
              </div>
              <div className="bg-card p-4">
                <dt className="text-xs text-muted-foreground">Private repos</dt>
                <dd
                  className={`mt-1 font-mono text-sm ${
                    info.entitlements.private_repos ? "text-ok" : "text-muted-foreground"
                  }`}
                >
                  {info.entitlements.private_repos ? "Yes" : "No"}
                </dd>
              </div>
            </dl>
          </section>
        </>
      ) : null}
    </div>
  );
}
