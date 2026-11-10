// The lines of the log have the keys of the Python services (aireuskadi-logger), because Loki and
// the dashboards of Grafana read them with `| json | level=~"ERROR|CRITICAL" | message=...`:
// `time` in ISO format, `level` as a capital word (not pino's number), `logger` and `message`
// (not pino's `msg`). The process id and the host name are left out.
import type { FastifyServerOptions } from "fastify";

const LEVELS: Record<string, string> = {
  trace: "DEBUG",
  debug: "DEBUG",
  info: "INFO",
  warn: "WARNING",
  error: "ERROR",
  fatal: "CRITICAL",
};

export const LOGGER = "air_quality_service";

// The names of the Python levels, which LOG_LEVEL accepts in the compose and in `.env`, and the
// ones of pino. An empty value is the default; a name that does not exist stops the start, so a
// typo is not a service that silently logs nothing.
const LEVEL_NAMES: Record<string, string> = {
  debug: "debug",
  info: "info",
  warning: "warn",
  warn: "warn",
  error: "error",
  critical: "fatal",
  fatal: "fatal",
  trace: "trace",
  silent: "silent",
};

export function normalizeLevel(value: string | undefined): string {
  const name = (value ?? "").trim().toLowerCase();
  if (name === "") return "info";
  const level = LEVEL_NAMES[name];
  if (!level) throw new Error(`LOG_LEVEL is not a level: ${JSON.stringify(value).slice(0, 40)}`);
  return level;
}

// The credentials of a URL (scheme://user:password@host) are hidden wherever they are, before the
// text is cut, so that a cut cannot leave half of a password: the same rule as aireuskadi-logger.
const CREDENTIALS = /(:\/\/[^/\s:@]+):[^@\s/]+@/g;

export function clean(text: string, limit: number): string {
  const hidden = text.replace(CREDENTIALS, "$1:***@");
  if (hidden.length <= limit) return hidden;
  return `${hidden.slice(0, limit)}...[truncated ${hidden.length - limit}]`;
}

export const MAX_EXCEPTION = 8000;

export function loggerOptions(level: string, stream?: { write(line: string): void }) {
  const options = {
    level,
    messageKey: "message",
    base: null,
    timestamp: () => `,"time":"${new Date().toISOString()}"`,
    formatters: {
      level: (label: string) => ({ level: LEVELS[label] ?? label.toUpperCase() }),
      // A line that names its own logger (the request log) keeps it; the others get the name of the service.
      log: (object: Record<string, unknown>) => ({ logger: LOGGER, ...object }),
    },
    ...(stream ? { stream } : {}),
  };
  return options as NonNullable<FastifyServerOptions["logger"]>;
}
