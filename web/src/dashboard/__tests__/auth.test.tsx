// Exercises the AuthProvider login/logout flow. api2 is fully mocked so no
// network or localStorage token juggling leaks between the client and the
// context — we drive `useAuth()` through a tiny consumer component.

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api2";
import { AuthProvider, useAuth } from "../auth";

const USER = { id: "u1", email: "user@test.dev" };
const PROJECTS = [
  { id: "p1", name: "Acme", tier: "free", private_repos_enabled: false },
  { id: "p2", name: "Beta", tier: "team", private_repos_enabled: true },
];

// The factory is hoisted above imports, so it may only reference values defined
// inside it. A module-local `token` lets get/setToken behave like the real
// localStorage-backed pair, which is what `hydrate()` depends on.
vi.mock("../api2", () => {
  let token: string | null = null;
  return {
    getToken: vi.fn(() => token),
    setToken: vi.fn((t: string | null) => {
      token = t;
    }),
    me: vi.fn(async () => ({
      user: { id: "u1", email: "user@test.dev" },
      projects: [
        { id: "p1", name: "Acme", tier: "free", private_repos_enabled: false },
        { id: "p2", name: "Beta", tier: "team", private_repos_enabled: true },
      ],
    })),
    login: vi.fn(async () => ({
      user: { id: "u1", email: "user@test.dev" },
      token: "jwt-abc",
    })),
    signup: vi.fn(async () => ({
      user: { id: "u1", email: "user@test.dev" },
      token: "jwt-abc",
    })),
    logout: vi.fn(async () => undefined),
    listProjects: vi.fn(async () => []),
  };
});

function Consumer() {
  const { user, activeProject, loading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user?.email ?? "none"}</span>
      <span data-testid="project">{activeProject?.name ?? "none"}</span>
      <button onClick={() => void login("user@test.dev", "pw12345678")}>
        do-login
      </button>
      <button onClick={() => void logout()}>do-logout</button>
    </div>
  );
}

function renderConsumer() {
  return render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>
  );
}

beforeEach(() => {
  localStorage.clear();
  // Reset the mocked token to logged-out between tests.
  vi.mocked(api.setToken)(null);
  vi.clearAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

describe("AuthProvider", () => {
  it("starts logged-out with no token and settles loading=false", async () => {
    renderConsumer();

    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("false")
    );
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(screen.getByTestId("project")).toHaveTextContent("none");
  });

  it("exposes the user + active project after login()", async () => {
    renderConsumer();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("false")
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "do-login" }));
    });

    await waitFor(() =>
      expect(screen.getByTestId("user")).toHaveTextContent(USER.email)
    );
    // hydrate() defaults the active project to the first one returned by me().
    expect(screen.getByTestId("project")).toHaveTextContent(PROJECTS[0].name);

    expect(vi.mocked(api.login)).toHaveBeenCalledWith(
      "user@test.dev",
      "pw12345678"
    );
    expect(vi.mocked(api.setToken)).toHaveBeenCalledWith("jwt-abc");
  });

  it("clears the user + active project on logout()", async () => {
    renderConsumer();
    await waitFor(() =>
      expect(screen.getByTestId("loading")).toHaveTextContent("false")
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "do-login" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("user")).toHaveTextContent(USER.email)
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "do-logout" }));
    });

    await waitFor(() =>
      expect(screen.getByTestId("user")).toHaveTextContent("none")
    );
    expect(screen.getByTestId("project")).toHaveTextContent("none");
    expect(vi.mocked(api.logout)).toHaveBeenCalled();
  });
});
