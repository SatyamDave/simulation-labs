import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./dashboard/auth";
import RequireAuth from "./dashboard/components/RequireAuth";
import DashboardLayout from "./dashboard/DashboardLayout";
import Login from "./dashboard/pages/Login";
import Signup from "./dashboard/pages/Signup";
import Runs from "./dashboard/pages/Runs";
import RunDetail from "./dashboard/pages/RunDetail";
import Flows from "./dashboard/pages/Flows";
import Settings from "./dashboard/pages/Settings";
import Billing from "./dashboard/pages/Billing";
import Members from "./dashboard/pages/Members";
import "./styles.css";

const el = document.getElementById("root");
if (!el) throw new Error("#root not found");

// The demo lives at "/" (unchanged). The hosted dashboard mounts under "/app"
// behind auth; "/login" and "/signup" are public. AuthProvider wraps everything
// so the demo stays auth-agnostic while the dashboard reads the session.
createRoot(el).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/app" element={<RequireAuth />}>
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
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
);
