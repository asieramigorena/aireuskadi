import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    // The tests that do not read the log do not print it.
    env: { LOG_LEVEL: "silent" },
  },
});
