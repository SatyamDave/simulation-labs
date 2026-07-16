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
  },
});
