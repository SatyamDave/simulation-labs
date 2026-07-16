// Vitest setup for the dashboard test suite. Registers @testing-library/jest-dom
// matchers on vitest's `expect` (the `/vitest` entrypoint also augments the
// `vitest` module's Assertion types so `.toBeInTheDocument()` etc. typecheck),
// and tears down the rendered DOM after every test.
//
// Orchestrator: wire this via vitest config `setupFiles: ['src/dashboard/test-setup.ts']`.

import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom@25 under vitest does not expose a `localStorage`, but the frozen
// api2.ts / auth.tsx read and write it directly. Install a minimal, spec-shaped
// in-memory Storage shim so those modules behave as they do in the browser.
if (typeof globalThis.localStorage === "undefined") {
  class MemoryStorage implements Storage {
    private store = new Map<string, string>();
    get length(): number {
      return this.store.size;
    }
    clear(): void {
      this.store.clear();
    }
    getItem(key: string): string | null {
      return this.store.has(key) ? this.store.get(key)! : null;
    }
    key(index: number): string | null {
      return Array.from(this.store.keys())[index] ?? null;
    }
    removeItem(key: string): void {
      this.store.delete(key);
    }
    setItem(key: string, value: string): void {
      this.store.set(key, String(value));
    }
  }
  const storage = new MemoryStorage();
  Object.defineProperty(globalThis, "localStorage", {
    value: storage,
    configurable: true,
  });
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "localStorage", {
      value: storage,
      configurable: true,
    });
  }
}

afterEach(() => {
  cleanup();
});
