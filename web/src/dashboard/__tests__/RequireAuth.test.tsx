// Route-guard behavior for <RequireAuth/>. `useAuth` is mocked so we can drive
// the three states (loading / unauthenticated / authenticated) directly, and a
// MemoryRouter provides the /login target + the protected <Outlet/> child.
//
// RequireAuth (owned by P3-B) is present in the tree, so it is imported
// statically here. Were it still missing, this whole suite would fail to
// resolve the import — see the report note.

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import RequireAuth from "../components/RequireAuth";
import { useAuth } from "../auth";

vi.mock("../auth", () => ({
  useAuth: vi.fn(),
}));

type AuthValue = ReturnType<typeof useAuth>;

// Full AuthState with sensible logged-out defaults; override per test.
function authState(over: Partial<AuthValue>): AuthValue {
  return {
    user: null,
    projects: [],
    activeProject: null,
    loading: false,
    login: vi.fn(async () => {}),
    signup: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
    setActiveProject: vi.fn(),
    refreshProjects: vi.fn(async () => {}),
    ...over,
  };
}

function renderGuard(value: AuthValue) {
  vi.mocked(useAuth).mockReturnValue(value);
  return render(
    <MemoryRouter initialEntries={["/app"]}>
      <Routes>
        <Route path="/app" element={<RequireAuth />}>
          <Route index element={<div>PROTECTED CONTENT</div>} />
        </Route>
        <Route path="/login" element={<div>LOGIN PAGE</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("RequireAuth", () => {
  it("shows a spinner while the session is loading", () => {
    renderGuard(authState({ loading: true }));

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("PROTECTED CONTENT")).not.toBeInTheDocument();
    expect(screen.queryByText("LOGIN PAGE")).not.toBeInTheDocument();
  });

  it("redirects to /login when unauthenticated", () => {
    renderGuard(authState({ user: null, loading: false }));

    expect(screen.getByText("LOGIN PAGE")).toBeInTheDocument();
    expect(screen.queryByText("PROTECTED CONTENT")).not.toBeInTheDocument();
  });

  it("renders the nested outlet when authenticated", () => {
    renderGuard(
      authState({ user: { id: "u1", email: "a@b.com" }, loading: false })
    );

    expect(screen.getByText("PROTECTED CONTENT")).toBeInTheDocument();
    expect(screen.queryByText("LOGIN PAGE")).not.toBeInTheDocument();
  });
});
