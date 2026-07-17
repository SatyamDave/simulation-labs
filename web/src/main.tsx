import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./dashboard/auth";
import RequireAuth from "./dashboard/components/RequireAuth";
import ErrorBoundary from "./dashboard/components/ErrorBoundary";
import Fallback from "./dashboard/components/Fallback";
import "./styles.css";

// Code-splitting: the demo `App` (route "/") stays eager so the landing paints
// immediately with no extra network round-trip. Everything behind auth — the
// dashboard shell and pages — plus the public auth pages are lazy-loaded, so the
// initial bundle no longer ships the whole dashboard. Each page becomes its own
// chunk fetched on first navigation, gated by the <Suspense fallback> below.
const DashboardLayout = lazy(() => import("./dashboard/DashboardLayout"));
const Login = lazy(() => import("./dashboard/pages/Login"));
const Signup = lazy(() => import("./dashboard/pages/Signup"));
const Runs = lazy(() => import("./dashboard/pages/Runs"));
const RunDetail = lazy(() => import("./dashboard/pages/RunDetail"));
const Flows = lazy(() => import("./dashboard/pages/Flows"));
const Settings = lazy(() => import("./dashboard/pages/Settings"));
const Billing = lazy(() => import("./dashboard/pages/Billing"));
const Members = lazy(() => import("./dashboard/pages/Members"));
const Terms = lazy(() => import("./legal/Terms"));
const Privacy = lazy(() => import("./legal/Privacy"));
const AcceptableUse = lazy(() => import("./legal/AcceptableUse"));

const el = document.getElementById("root");
if (!el) throw new Error("#root not found");

// The demo lives at "/" (unchanged, eager). The hosted dashboard mounts under
// "/app" behind auth; "/login" and "/signup" are public. AuthProvider wraps
// everything so the demo stays auth-agnostic while the dashboard reads the
// session. <Suspense> (top-level) shows the accessible Fallback while any lazy
// chunk loads; <ErrorBoundary> is scoped to the "/app" dashboard subtree so a
// render error there swaps in a recover card instead of a white screen, while a
// crash never masks the eager landing or the public auth pages.
createRoot(el).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<Fallback />}>
          <Routes>
            <Route path="/" element={<App />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            {/* Public legal pages — linked from the app footer and dashboard. */}
            <Route path="/legal/terms" element={<Terms />} />
            <Route path="/legal/privacy" element={<Privacy />} />
            <Route path="/legal/acceptable-use" element={<AcceptableUse />} />
            <Route
              path="/app"
              element={
                <ErrorBoundary>
                  <RequireAuth />
                </ErrorBoundary>
              }
            >
              <Route element={<DashboardLayout />}>
                <Route index element={<Navigate to="runs" replace />} />
                <Route path="runs" element={<Runs />} />
                <Route path="runs/:runId" element={<RunDetail />} />
                <Route path="flows" element={<Flows />} />
                <Route path="members" element={<Members />} />
                <Route path="billing" element={<Billing />} />
                <Route path="settings" element={<Settings />} />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
);
