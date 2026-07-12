// Compact NemoClaw policy-sandbox line. Fetches GET /policy once; renders
// nothing when the endpoint is absent / 503 / carries no usable policy info,
// so offline and un-sandboxed demos stay clean. One quiet mono line, v3-style.

import { useEffect, useState } from "react";
import { getPolicy, type PolicyInfo } from "../api";

export function PolicyPanel() {
  const [policy, setPolicy] = useState<PolicyInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPolicy().then((p) => {
      if (!cancelled) setPolicy(p);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!policy) return null;
  const summary = policy.summary ?? undefined;
  const active = Boolean(policy.active);
  // Without a parsed summary AND without an active gateway there is nothing
  // trustworthy to show — stay silent rather than implying enforcement.
  if (!summary && !active) return null;

  const preset = summary?.preset;
  const methods = summary?.allowed_methods ?? [];
  const getOnly =
    methods.length > 0 &&
    methods.every((m) => ["GET", "HEAD"].includes(m.toUpperCase()));

  return (
    <div
      className="flex items-center gap-x-3 gap-y-1 flex-wrap font-mono text-xs text-muted-foreground min-w-0"
      role="status"
    >
      <svg
        className="w-3.5 h-3.5 shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z"
        />
      </svg>
      <span className="min-w-0">
        <span className="font-medium text-foreground">
          NemoClaw sandbox{preset ? `: ${preset}` : ""}
        </span>
        {getOnly
          ? " — GET-only browsing, submits blocked at the network layer"
          : summary?.denied_by_default
            ? " — denied by default, allowlisted actions only"
            : " — policy gateway in the loop"}
      </span>
      {methods.length > 0 && (
        <span
          className="whitespace-nowrap"
          title="HTTP methods the policy allows"
        >
          {methods.join(" · ")}
        </span>
      )}
      <span className="ml-auto inline-flex items-center gap-1.5 whitespace-nowrap">
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            active ? "bg-ok" : "bg-idle/40"
          }`}
          aria-hidden="true"
        />
        gateway {active ? "active" : "inactive"}
        {policy.enforced != null && (
          <> · {policy.enforced ? "enforced" : "advisory"}</>
        )}
      </span>
    </div>
  );
}
