// Entry point of the container: reads the settings from the environment, opens the pool and listens.
import { buildApp } from "./app.js";
import { createPool } from "./db.js";

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL is not set (see .env.example)");
  process.exit(1);
}

// The pool is made before the application, and the application owns the log: until it exists a
// lost connection has nowhere to go.
let report: (error: Error & { code?: string }) => void = () => undefined;
const pool = createPool(url, (error) => report(error));
const app = await buildApp({ db: pool });
// Only the code of the error: its message can name the host and the user.
report = (error) => app.log.error({ code: error.code }, "database connection lost");

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    void app.close().then(() => pool.close()).then(() => process.exit(0));
  });
}

await app.listen({ host: "0.0.0.0", port: Number(process.env.PORT ?? 8000) });
