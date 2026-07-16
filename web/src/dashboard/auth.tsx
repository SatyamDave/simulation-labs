// Auth context for the dashboard. Holds the session token + user + projects,
// exposes login/signup/logout and the active project. FROZEN — pages consume
// `useAuth()`; do not change the shape.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import * as api from "./api2";
import type { Project, User } from "./types2";

interface AuthState {
  user: User | null;
  projects: Project[];
  activeProject: Project | null;
  loading: boolean; // true while restoring the session on mount
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setActiveProject: (projectId: string) => void;
  refreshProjects: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);
const ACTIVE_KEY = "sl_active_project";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeId, setActiveId] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_KEY)
  );
  const [loading, setLoading] = useState<boolean>(Boolean(api.getToken()));

  const hydrate = useCallback(async () => {
    if (!api.getToken()) {
      setLoading(false);
      return;
    }
    try {
      const { user: u, projects: ps } = await api.me();
      setUser(u);
      setProjects(ps);
      setActiveId((prev) => prev ?? ps[0]?.id ?? null);
    } catch {
      api.setToken(null);
      setUser(null);
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  const afterAuth = useCallback((token: string) => {
    api.setToken(token);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await api.login(email, password);
      afterAuth(r.token);
      await hydrate();
    },
    [afterAuth, hydrate]
  );

  const signup = useCallback(
    async (email: string, password: string) => {
      const r = await api.signup(email, password);
      afterAuth(r.token);
      await hydrate();
    },
    [afterAuth, hydrate]
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* best-effort */
    }
    api.setToken(null);
    setUser(null);
    setProjects([]);
    setActiveId(null);
    localStorage.removeItem(ACTIVE_KEY);
  }, []);

  const setActiveProject = useCallback((projectId: string) => {
    setActiveId(projectId);
    localStorage.setItem(ACTIVE_KEY, projectId);
  }, []);

  const refreshProjects = useCallback(async () => {
    const ps = await api.listProjects();
    setProjects(ps);
    setActiveId((prev) => prev ?? ps[0]?.id ?? null);
  }, []);

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeId) ?? projects[0] ?? null,
    [projects, activeId]
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      projects,
      activeProject,
      loading,
      login,
      signup,
      logout,
      setActiveProject,
      refreshProjects,
    }),
    [user, projects, activeProject, loading, login, signup, logout, setActiveProject, refreshProjects]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
