// What the service needs from the database: ask and read the rows. The routes only know this
// interface, so the tests can give them a connection inside a transaction that is rolled back.
import pg from "pg";

export interface Db {
  query<R = Record<string, unknown>>(text: string, params?: unknown[]): Promise<{ rows: R[] }>;
}

export interface Pool extends Db {
  close(): Promise<void>;
}

/**
 * The pool of the service. It is small: 5 connections, a request that finds none waits 5 seconds
 * and fails, and a query that takes more than 5 seconds is cut by the server itself (the Python
 * services have 5 and 5 more on a peak). The URL must be the one of the read-only role, never the
 * owner of the database: `default_transaction_read_only` is only a default that a session can lift.
 *
 * A connection that is idle when Postgres restarts or the network fails makes the pool emit
 * `error`; without a listener Node ends the process. `onError` is told, and the pool opens a new
 * connection the next time it is asked.
 */
export function createPool(url: string, onError: (error: Error) => void): Pool {
  const pool = new pg.Pool({
    connectionString: url,
    max: 5,
    connectionTimeoutMillis: 5000,
    options: "-c statement_timeout=5000 -c default_transaction_read_only=on",
  });
  pool.on("error", onError);
  return {
    query: (text, params) => pool.query(text, params as never[]) as never,
    close: () => pool.end(),
  };
}
