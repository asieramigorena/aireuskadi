import { expect, test, vi } from "vitest";
import { buildApp } from "../src/app.js";
import { fakeDb, logSink } from "./helpers.js";

// The dashboards of Grafana read these lines with `| json | level=~"ERROR|CRITICAL"`,
// `{{.logger}}`, `{{.message}}`: the keys have to be the ones of the Python services.

test("a request leaves one line with the keys of the Python services", async () => {
  const sink = logSink();
  const app = await buildApp({ db: fakeDb(), logStream: sink.stream, logLevel: "info" });

  await app.inject("/nothing-here");

  expect(sink.records()).toHaveLength(1);
  const line = sink.records()[0];
  // `reqId` is the one extra key: it ties the line of a failure to the line of its request.
  expect(Object.keys(line).sort()).toEqual(
    ["duration_ms", "level", "logger", "message", "method", "path", "reqId", "status", "time"],
  );
  expect(line).toMatchObject({
    level: "INFO",
    logger: "air_quality_service.access",
    message: "request",
    method: "GET",
    path: "/nothing-here",
    status: 404,
  });
  expect(line.time).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}(Z|\+00:00)$/);
  expect(typeof line.duration_ms).toBe("number");
  // Not pino's own: the level is a word, the message is `message`, and no process data is added.
  for (const key of ["msg", "pid", "hostname", "req", "res"]) expect(line).not.toHaveProperty(key);
});

test("the query string and the headers never reach the log", async () => {
  const sink = logSink();
  const app = await buildApp({ db: fakeDb(), logStream: sink.stream, logLevel: "info" });

  await app.inject({
    url: "/nothing-here?token=abc123&name=typed-by-somebody",
    headers: { authorization: "Bearer header-secret", cookie: "sid=cookie-secret" },
  });

  const text = sink.lines.join("");
  for (const secret of ["abc123", "typed-by-somebody", "header-secret", "cookie-secret"]) {
    expect(text).not.toContain(secret);
  }
  expect(sink.records()[0].path).toBe("/nothing-here");
});

test("the checks of the compose, which come every few seconds, are only in the log at DEBUG", async () => {
  const quiet = logSink();
  await (await buildApp({ db: fakeDb(), logStream: quiet.stream, logLevel: "info" })).inject("/health");
  expect(quiet.lines).toEqual([]);

  const verbose = logSink();
  await (await buildApp({ db: fakeDb(), logStream: verbose.stream, logLevel: "debug" })).inject("/health");
  expect(verbose.records()).toHaveLength(1);
  expect(verbose.records()[0]).toMatchObject({ level: "DEBUG", path: "/health", status: 200 });
});

test("a warning and a failure use the names of the Python levels", async () => {
  const sink = logSink();
  const app = await buildApp({ db: fakeDb(), logStream: sink.stream, logLevel: "info" });

  app.log.warn("a warning");
  app.log.error("a failure");
  app.log.fatal("the end");

  expect(sink.records().map((r) => r.level)).toEqual(["WARNING", "ERROR", "CRITICAL"]);
  expect(sink.records().every((r) => r.logger === "air_quality_service")).toBe(true);
});

test("the level comes from LOG_LEVEL, as in the Python services", async () => {
  vi.stubEnv("LOG_LEVEL", "DEBUG");
  try {
    const sink = logSink();
    const app = await buildApp({ db: fakeDb(), logStream: sink.stream });

    await app.inject("/health");

    expect(sink.records()).toHaveLength(1);
  } finally {
    vi.unstubAllEnvs();
  }
});

test.each([
  ["WARNING", false],
  ["warning", false],
  ["CRITICAL", false],
  ["ERROR", false],
  ["INFO", true],
  ["", true],
])("LOG_LEVEL=%j is accepted, as it is by the Python services", async (value, writesRequests) => {
  vi.stubEnv("LOG_LEVEL", value);
  try {
    const sink = logSink();
    const app = await buildApp({ db: fakeDb(), logStream: sink.stream });

    await app.inject("/nothing-here");

    expect(sink.records().length > 0).toBe(writesRequests);
  } finally {
    vi.unstubAllEnvs();
  }
});

test("a level that does not exist stops the start with a clear message", async () => {
  vi.stubEnv("LOG_LEVEL", "LOUD");
  try {
    await expect(buildApp({ db: fakeDb() })).rejects.toThrow(/LOG_LEVEL/);
  } finally {
    vi.unstubAllEnvs();
  }
});

test("the credentials of a URL in the reason of a failure are hidden, and a long reason is cut", async () => {
  const sink = logSink();
  const app = await buildApp({ db: fakeDb(), logStream: sink.stream, logLevel: "info" });
  app.get("/boom", async () => {
    throw new Error("could not connect to postgresql://reader:SecretPass9@db-host:5432/aireuskadi " + "x".repeat(20_000));
  });

  await app.inject("/boom");

  const failure = sink.records().find((r) => r.level === "ERROR");
  expect(sink.lines.join("")).not.toContain("SecretPass9");
  expect(String(failure?.exception)).toContain("postgresql://reader:***@db-host");
  expect(String(failure?.exception).length).toBeLessThan(8_100);
});
