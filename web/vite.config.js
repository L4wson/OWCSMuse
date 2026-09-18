import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs separately (python -m owcsmuse serve). In development the dev
// server proxies to it so the app is same-origin; in a build, VITE_API_BASE
// points at wherever the service lives.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ["/ask", "/query", "/suggestions", "/healthz"].map((path) => [
        path,
        { target: process.env.OWCS_API_URL || "http://127.0.0.1:8000", changeOrigin: true },
      ]),
    ),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.js"],
    include: ["tests/**/*.test.jsx"],
    restoreMocks: true,
  },
});
