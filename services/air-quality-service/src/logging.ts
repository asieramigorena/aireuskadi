// The lines of the log have the keys of the Python services, because Loki and the dashboards of
// Grafana read them: `time` (ISO), `level` as a word in capitals, `logger` and `message`.
import type { FastifyServerOptions } from "fastify";

export const LOGGER = "air_quality_service";

// pino's names of the levels -> the names of Python.
const PYTHON_LEVEL: Record<string, string> = {
  trace: "DEBUG",
  debug: "DEBUG",
  info: "INFO",
  warn: "WARNING",
  error: "ERROR",
  fatal: "CRITICAL",
};

// LOG_LEVEL is written as in Python (WARNING, CRITICAL...): the name that pino gives it.
const PINO_LEVEL: Record<string, string> = { warning: "warn", critical: "fatal" };

export function pinoLevel(value: string | undefined): string {
  const name = (value || "info").toLowerCase();
  return PINO_LEVEL[name] ?? name;
}

// The password of a URL (postgresql://user:password@host) is hidden, and a very long text is cut.
export function clean(text: string): string {
  return text.replace(/(:\/\/[^/\s:@]+):[^@\s/]+@/g, "$1:***@").slice(0, 8000);
}

export function loggerOptions(level: string, stream?: { write(line: string): void }) {
  return {
    level,
    messageKey: "message",
    base: null, // no process id, no host name
    timestamp: () => `,"time":"${new Date().toISOString()}"`,
    formatters: {
      level: (label: string) => ({ level: PYTHON_LEVEL[label] ?? label.toUpperCase() }),
      log: (object: Record<string, unknown>) => ({ logger: LOGGER, ...object }),
    },
    ...(stream ? { stream } : {}),
  } as NonNullable<FastifyServerOptions["logger"]>;
}
