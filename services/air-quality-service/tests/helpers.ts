import type { Db } from "../src/db.js";

/** A database that answers with the rows it is given and remembers what it was asked. */
export function fakeDb(rows: unknown[] = []): Db & { asked: string[] } {
  const asked: string[] = [];
  return {
    asked,
    async query(text: string) {
      asked.push(text);
      return { rows } as { rows: never[] };
    },
  };
}

/** A database that fails the way a lost connection does, with a message that must not reach a client. */
export function brokenDb(message = 'password authentication failed for user "reader_secret"'): Db {
  return {
    async query() {
      throw new Error(message);
    },
  };
}

/** Where the log lines go in a test: one JSON object per line. */
export function logSink() {
  const lines: string[] = [];
  return {
    stream: { write: (line: string) => void lines.push(line) },
    lines,
    records: () => lines.map((line) => JSON.parse(line) as Record<string, unknown>),
  };
}
