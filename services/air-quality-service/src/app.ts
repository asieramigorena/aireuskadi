// The application: puts the pieces together. It does not open the database or listen on a port,
// so the tests can build it with the connection and the log they want.
import swagger from "@fastify/swagger";
import Fastify, { LogController } from "fastify";
import type { Db } from "./db.js";
import { LOGGER, loggerOptions, normalizeLevel } from "./logging.js";
import { errorHandler, frameworkErrors, notFoundHandler, problem } from "./problems.js";
import { stationRoutes } from "./stations.js";

export const HEALTH_PATH = "/health";

export interface Options {
  db: Db;
  /** Where the log lines go (a test reads them); the standard output if it is not given. */
  logStream?: { write(line: string): void };
  logLevel?: string;
}

export async function buildApp({ db, logStream, logLevel }: Options) {
  const app = Fastify({
    logger: loggerOptions(normalizeLevel(logLevel ?? process.env.LOG_LEVEL), logStream),
    frameworkErrors,
    // One line per request, written below with the same fields as the Python services.
    logController: new LogController({ disableRequestLogging: true }),
  });
  app.setErrorHandler(errorHandler);
  app.setNotFoundHandler(notFoundHandler);

  // The query string and the headers are not logged: they can carry what the client typed. The
  // checks of the compose come every few seconds, so they are only in the log at DEBUG.
  app.addHook("onResponse", async (request, reply) => {
    const path = request.url.split("?")[0];
    const record = {
      logger: `${LOGGER}.access`,
      method: request.method,
      path,
      status: reply.statusCode,
      duration_ms: Math.round(reply.elapsedTime * 10) / 10,
    };
    if (path === HEALTH_PATH) request.log.debug(record, "request");
    else request.log.info(record, "request");
  });

  // Awaited: the routes that are added after it have to be seen by it.
  await app.register(swagger, {
    openapi: {
      openapi: "3.0.3",
      info: { title: "AirEuskadi Air Quality Service", version: "0.1.0" },
    },
  });
  // The gateway reads this document to merge it with the others, so it is always served. It and
  // the check of the compose are not in it.
  app.get("/openapi.json", { schema: { hide: true } }, async () => app.swagger());

  app.get(HEALTH_PATH, { schema: { hide: true } }, async (_request, reply) => {
    try {
      await db.query("SELECT 1");
    } catch {
      // A fixed text: the reason (a host, a user) is not for whoever asks.
      return problem(reply, 503, "The service is not ready.");
    }
    return { status: "ok" };
  });

  await app.register(stationRoutes, { db });

  return app;
}
