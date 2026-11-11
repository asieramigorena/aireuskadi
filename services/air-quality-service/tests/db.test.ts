import type { EventEmitter } from "node:events";
import { expect, test, vi } from "vitest";

// `vi.mock` is moved to the top of the file: what it uses has to be made there too.
const created = vi.hoisted(() => [] as { options: Record<string, unknown>; pool: EventEmitter }[]);

vi.mock("pg", async () => {
  const { EventEmitter } = await import("node:events");
  class Pool extends EventEmitter {
    constructor(options: Record<string, unknown>) {
      super();
      created.push({ options, pool: this });
    }
    query = vi.fn(async () => ({ rows: [] }));
    end = vi.fn(async () => undefined);
  }
  return { default: { Pool } };
});

const { createPool } = await import("../src/db.js");

test("the pool is small, gives up waiting after 5 seconds and the server cuts a query at 5 seconds", () => {
  createPool("postgresql://reader:pw@db:5432/aireuskadi", () => undefined);

  const { options } = created.at(-1)!;
  expect(options.max).toBe(5);
  expect(options.connectionTimeoutMillis).toBe(5000);
  expect(options.options).toContain("-c statement_timeout=5000");
  expect(options.options).toContain("-c default_transaction_read_only=on");
});

test("a connection that is lost while it is idle is reported and does not stop the process", () => {
  const reported: unknown[] = [];
  createPool("postgresql://reader:pw@db:5432/aireuskadi", (error) => reported.push(error));
  const { pool } = created.at(-1)!;

  // An EventEmitter that emits "error" with no listener throws: that is what would end the process.
  expect(() => pool.emit("error", Object.assign(new Error("terminating connection"), { code: "57P01" }))).not.toThrow();

  expect(reported).toHaveLength(1);
});
