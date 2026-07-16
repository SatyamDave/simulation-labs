import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Ghostpanel frontend. API base is read at runtime from import.meta.env.VITE_API_BASE
// (see src/api.ts); nothing about the backend is baked in here.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        // Split the long-lived framework/vendor code out of the app entry so it
        // caches independently and the main entry only carries app code. React
        // and its router/animation deps rarely change; app code changes often.
        manualChunks: {
          "vendor-react": [
            "react",
            "react-dom",
            "react-router-dom",
          ],
          "vendor-motion": ["framer-motion"],
        },
      },
    },
  },
});
