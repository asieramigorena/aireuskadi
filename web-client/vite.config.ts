import { defineConfig } from "vitest/config";

export default defineConfig({
  server: {
    // In development the page and the gateway are on different ports: the browser asks Vite and
    // Vite asks the gateway, so the gateway needs no CORS yet.
    // The gateway: the API, and the admin pages and Grafana behind it.
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/admin": "http://127.0.0.1:8080",
      "/user": "http://127.0.0.1:8080",
      "/grafana": "http://127.0.0.1:8080",
    },
  },
  test: {
    environment: "happy-dom",
  },
});
