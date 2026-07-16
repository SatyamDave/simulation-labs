// Route guard for the dashboard. While the session is being restored we show a
// small spinner; once resolved we either bounce to /login or render the nested
// route via <Outlet/>.

import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

export default function RequireAuth() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background"
        role="status"
        aria-live="polite"
        aria-label="Loading"
      >
        <span
          className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-foreground"
          aria-hidden="true"
        />
        <span className="sr-only">Loading…</span>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
