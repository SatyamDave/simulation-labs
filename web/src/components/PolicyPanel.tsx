// Compact NemoClaw policy-sandbox strip. Fetches GET /policy once; renders
// nothing when the endpoint is absent / 503 / carries no usable policy info,
// so offline and un-sandboxed demos stay clean.

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
    methods.length > 0 && methods.every((m) => ["GET", "HEAD"].includes(m.toUpperCase()));

  return (
    <div className="policy" role="status">
      <span className="policy__shield" aria-hidden="true">
        🛡
      </span>
      <span className="policy__text">
        <b>NemoClaw sandbox{preset ? `: ${preset}` : ""}</b>
        {getOnly
          ? " — GET-only browsing, submits blocked at the network layer"
          : summary?.denied_by_default
          ? " — denied by default, allowlisted actions only"
          : " — policy gateway in the loop"}
      </span>
      {methods.length > 0 && (
        <span className="policy__methods" title="HTTP methods the policy allows">
          {methods.join(" · ")}
        </span>
      )}
      <span className={`ws ${active ? "ws--open" : "ws--closed"} policy__gateway`}>
        <span className="ws__dot" /> gateway {active ? "active" : "inactive"}
        {policy.enforced != null && (
          <> · {policy.enforced ? "enforced" : "advisory"}</>
        )}
      </span>
    </div>
  );
}
