import { defineConfig } from "vitest/config";

export default defineConfig({
  server: {
    // In development the page and the gateway are on different ports: the browser asks Vite and
    // Vite asks the gateway, so the gateway needs no CORS yet.
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
  test: {
    environment: "happy-dom",
  },
});
