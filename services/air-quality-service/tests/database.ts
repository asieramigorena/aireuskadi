// Tests against a real PostgreSQL + PostGIS, inside a transaction that is rolled back at the end,
// so that what a test writes is never seen by another one. They never use the database of the
// application: like the Python tests, they use `<name>_test`, which `pytest packages/db` creates
// the first time. Without DATABASE_URL (the CI) they are skipped.
import pg from "pg";
import { test as base } from "vitest";
import type { Db } from "../src/db.js";

export function testDatabaseUrl(): string | undefined {
  const value = process.env.DATABASE_URL;
  if (!value) return undefined;
  const url = new URL(value);
  if (!url.pathname.endsWith("_test")) url.pathname += "_test";
  // Never a database that is not the one of the tests, whatever the URL looks like.
  if (!/^\/[^/]+_test$/.test(url.pathname)) return undefined;
  return url.toString();
}

export const hasDatabase = testDatabaseUrl() !== undefined;

const withDatabase = base.extend<{ db: Db }>({
  db: async ({ skip }, use) => {
    const client = new pg.Client({ connectionString: testDatabaseUrl() });
    try {
      await client.connect();
    } catch {
      // Like the Python plugin: a server that is down, or a test database that was never made
      // (`uv run pytest packages/db` makes it), is a skipped test with its reason, not a red one.
      await client.end().catch(() => undefined);
      skip("the test database cannot be reached: run `uv run --env-file .env pytest packages/db` once");
    }
    await client.query("BEGIN");
    try {
      await use({ query: (text, params) => client.query(text, params as never[]) as never });
    } finally {
      await client.query("ROLLBACK");
      await client.end();
    }
  },
});

/** A test that gets `db`; it is skipped when there is no database to run it on. */
export const dbTest = withDatabase.skipIf(!hasDatabase);
