// Unit tests for the frozen /v2 API client. `fetch` is stubbed globally; we
// assert URL/method/headers/body shaping and error translation — no network.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  getToken,
  listRuns,
  login,
  me,
  setToken,
} from "../api2";

// Minimal Response stand-in — only the fields `req()` in api2 actually reads.
function res(
  body: unknown,
  init: { ok?: boolean; status?: number; statusText?: string } = {}
): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? "OK",
    json: async () => body,
  } as unknown as Response;
}

const mockFetch = vi.fn();

beforeEach(() => {
  localStorage.clear();
  mockFetch.mockReset();
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("login", () => {
  it("POSTs to /v2/auth/login with a JSON body and returns the parsed response", async () => {
    const payload = {
      user: { id: "u1", email: "a@b.com" },
      token: "jwt-1",
    };
    mockFetch.mockResolvedValueOnce(res(payload));

    const out = await login("a@b.com", "pw12345678");

    expect(out).toEqual(payload);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    const [url, opts] = mockFetch.mock.calls[0];
    expect(String(url)).toContain("/v2/auth/login");
    expect(opts.method).toBe("POST");
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(opts.body)).toEqual({
      email: "a@b.com",
      password: "pw12345678",
    });
  });

  it("throws an ApiError carrying the `detail` message and status on a non-ok response", async () => {
    mockFetch.mockResolvedValueOnce(
      res({ detail: "invalid credentials" }, {
        ok: false,
        status: 401,
        statusText: "Unauthorized",
      })
    );

    const err = await login("a@b.com", "nope").catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    expect((err as ApiError).message).toBe("invalid credentials");
  });

  it("falls back to `<status> <statusText>` when the error body is not JSON", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response);

    const err = await login("a@b.com", "x").catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
    expect((err as ApiError).message).toBe("500 Internal Server Error");
  });
});

describe("token storage", () => {
  it("round-trips getToken/setToken through localStorage", () => {
    expect(getToken()).toBeNull();

    setToken("abc123");
    expect(getToken()).toBe("abc123");
    expect(localStorage.getItem("sl_token")).toBe("abc123");

    setToken(null);
    expect(getToken()).toBeNull();
    expect(localStorage.getItem("sl_token")).toBeNull();
  });
});

describe("listRuns", () => {
  it("builds the project_id / flow / limit query string", async () => {
    mockFetch.mockResolvedValueOnce(res([]));

    await listRuns("proj-9", { flow: "checkout", limit: 25 });

    const url = String(mockFetch.mock.calls[0][0]);
    expect(url).toContain("/v2/runs?");
    expect(url).toContain("project_id=proj-9");
    expect(url).toContain("flow=checkout");
    expect(url).toContain("limit=25");
  });

  it("omits optional params when not supplied", async () => {
    mockFetch.mockResolvedValueOnce(res([]));

    await listRuns("proj-1");

    const url = String(mockFetch.mock.calls[0][0]);
    expect(url).toContain("project_id=proj-1");
    expect(url).not.toContain("flow=");
    expect(url).not.toContain("limit=");
  });
});

describe("authorization header", () => {
  it("attaches `Bearer <token>` when a token is stored", async () => {
    setToken("mytoken");
    mockFetch.mockResolvedValueOnce(res({ user: { id: "u1", email: "a@b.com" }, projects: [] }));

    await me();

    const opts = mockFetch.mock.calls[0][1];
    expect(opts.headers["Authorization"]).toBe("Bearer mytoken");
  });

  it("omits the Authorization header when no token is stored", async () => {
    mockFetch.mockResolvedValueOnce(res({ user: { id: "u1", email: "a@b.com" }, projects: [] }));

    await me();

    const opts = mockFetch.mock.calls[0][1];
    expect(opts.headers["Authorization"]).toBeUndefined();
  });
});
