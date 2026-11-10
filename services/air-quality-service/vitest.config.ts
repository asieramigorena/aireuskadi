import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    // The tests with a database all write the same rows of test (the municipality 98001) in a
    // transaction that stays open until the end of the test: two files at the same time wait for each
    // other and PostgreSQL ends one with "deadlock detected". One file at a time; they are quick.
    fileParallelism: false,
    // The tests that do not read the log do not print it.
    env: { LOG_LEVEL: "silent" },
  },
});
