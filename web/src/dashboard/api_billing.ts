// Typed client for the Phase-4 billing + members endpoints (/v2). Reuses the
// Bearer-token transport from ./api2 (API_BASE + getToken + ApiError) so auth,
// base-URL resolution, and error shape stay identical to the rest of the app.
// Pages consume these fns; ApiError.status lets the UI branch on 402/404/409.

import { API_BASE, getToken, ApiError } from "./api2";
import type { Tier } from "./types2";

// ---- shapes (mirror the backend billing/members routers) ----

// Serialized form of billing/entitlements.py::Entitlements. -1 means unlimited.
export interface Entitlements {
  tier: Tier;
  label: string;
  price_display: string;
  max_flows: number;
  max_runs_per_month: number;
  max_seats: number;
  private_repos: boolean;
}

export interface BillingUsage {
  runs_this_period: number;
  seats: number;
}

export interface BillingInfo {
  tier: Tier;
  entitlements: Entitlements;
  usage: BillingUsage;
  stripe_configured: boolean;
}

export interface CheckoutUrls {
  success_url: string;
  cancel_url: string;
}

export interface PortalUrls {
  return_url: string;
}

export interface RedirectUrl {
  url: string;
}

export type MemberRole = "owner" | "member";

export interface Member {
  user_id: string;
  email: string;
  role: MemberRole;
}

// ---- transport (mirrors api2's private `req` helper) ----

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- billing ----

export const getBilling = (projectId: string) =>
  req<BillingInfo>("GET", `/v2/projects/${projectId}/billing`);

export const startCheckout = (projectId: string, urls: CheckoutUrls) =>
  req<RedirectUrl>("POST", `/v2/projects/${projectId}/billing/checkout`, urls);

export const openPortal = (projectId: string, urls: PortalUrls) =>
  req<RedirectUrl>("POST", `/v2/projects/${projectId}/billing/portal`, urls);

// ---- members ----

export const listMembers = (projectId: string) =>
  req<Member[]>("GET", `/v2/projects/${projectId}/members`);

export const addMember = (projectId: string, email: string, role?: MemberRole) =>
  req<Member>("POST", `/v2/projects/${projectId}/members`, { email, role });

export const removeMember = (projectId: string, userId: string) =>
  req<void>("DELETE", `/v2/projects/${projectId}/members/${userId}`);
