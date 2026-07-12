import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Ghostpanel frontend. API base is read at runtime from import.meta.env.VITE_API_BASE
// (see src/api.ts); nothing about the backend is baked in here.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
