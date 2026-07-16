import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dashboard tests run in jsdom. test-setup registers jest-dom matchers, RTL
// cleanup, and a localStorage shim (jsdom under vitest exposes none).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/dashboard/test-setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      // text = human-readable CI log; json-summary = machine-readable total for
      // dashboards / future gate tooling.
      reporter: ["text", "json-summary"],
      // Measure every source file (not just imported ones) so untested pages
      // count against us and the floor stays honest as the suite grows.
      all: true,
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.{test,spec}.{ts,tsx}",
        "src/dashboard/test-setup.ts",
        "src/**/*.d.ts",
      ],
      // Floors sit just under the measured 2026-07 totals so the gate passes
      // today while ratcheting protects against regressions. See docs/testing.md.
      thresholds: {
        statements: 2,
        branches: 50,
        functions: 25,
        lines: 2,
      },
    },
  },
});
