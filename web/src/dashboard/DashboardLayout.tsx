// App chrome for the hosted dashboard: a persistent sidebar (nav + project
// switcher) with the top bar carrying the signed-in email, a theme toggle, and
// logout. Renders the active page through <Outlet/>. Dark/light aware — mirrors
// the demo's `.dark` html-class theme pattern (see web/src/App.tsx).

import { useCallback, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import { ProjectSwitcher } from "./components/ProjectSwitcher";

const NAV = [
  { to: "/app/runs", label: "Runs" },
  { to: "/app/flows", label: "Flows" },
  { to: "/app/members", label: "Members" },
  { to: "/app/billing", label: "Billing" },
  { to: "/app/settings", label: "Settings" },
] as const;

/** Dark mode on a `.dark` html class; initial value set pre-paint in index.html. */
function useTheme(): { dark: boolean; toggle: () => void } {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );
  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("theme", next ? "dark" : "light");
      return next;
    });
  }, []);
  return { dark, toggle };
}

function ThemeToggle({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-hover transition-colors"
    >
      {dark ? (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m9.9 9.9l1.4 1.4M3 12h2m14 0h2M5.6 18.4l1.4-1.4m9.9-9.9l1.4-1.4M16 12a4 4 0 11-8 0 4 4 0 018 0z"
          />
        </svg>
      ) : (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
          />
        </svg>
      )}
    </button>
  );
}

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const { dark, toggle } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  const isActive = (to: string) =>
    location.pathname === to || location.pathname.startsWith(to + "/");

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col md:flex-row">
      {/* Sidebar */}
      <aside className="md:w-60 md:min-h-screen border-b md:border-b-0 md:border-r border-border flex flex-col">
        <div className="px-5 h-12 flex items-center border-b border-border">
          <Link
            to="/app/runs"
            className="font-mono text-sm hover:opacity-70 transition-opacity"
          >
            simulation labs
          </Link>
        </div>

        <div className="px-4 py-4 border-b border-border">
          <ProjectSwitcher />
        </div>

        <nav className="flex-1 p-3 flex md:flex-col gap-1" aria-label="Dashboard">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={isActive(item.to) ? "page" : undefined}
              className={
                "px-3 py-2 rounded-lg text-sm transition-colors " +
                (isActive(item.to)
                  ? "bg-hover text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-hover")
              }
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-40 bg-background border-b border-border">
          <div className="px-6 h-12 flex items-center justify-end gap-4">
            {user && (
              <span
                className="text-xs text-muted-foreground truncate max-w-[16rem]"
                title={user.email}
              >
                {user.email}
              </span>
            )}
            <ThemeToggle dark={dark} toggle={toggle} />
            <button
              type="button"
              onClick={() => void handleLogout()}
              className="px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-hover transition-colors"
            >
              Log out
            </button>
          </div>
        </header>

        <main className="flex-1 min-w-0">
          <div className="mx-auto max-w-5xl px-6 py-8">
            <Outlet />
          </div>
        </main>

        <footer className="border-t border-border px-6 py-6">
          <nav
            aria-label="Legal"
            className="mx-auto max-w-5xl flex flex-wrap items-baseline gap-x-5 gap-y-1 text-xs text-muted-foreground"
          >
            <Link to="/legal/terms" className="hover:text-foreground transition-colors">
              Terms
            </Link>
            <Link to="/legal/privacy" className="hover:text-foreground transition-colors">
              Privacy
            </Link>
            <Link
              to="/legal/acceptable-use"
              className="hover:text-foreground transition-colors"
            >
              Acceptable Use
            </Link>
          </nav>
        </footer>
      </div>
    </div>
  );
}
