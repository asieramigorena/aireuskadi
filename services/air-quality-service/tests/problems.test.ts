import { expect, test } from "vitest";
import { buildApp } from "../src/app.js";
import { fakeDb, logSink } from "./helpers.js";

test("a path that does not exist is a problem document", async () => {
  const app = await buildApp({ db: fakeDb() });

  const response = await app.inject("/nothing-here");

  expect(response.statusCode).toBe(404);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json()).toEqual({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Not Found",
  });
});

test("a trailing slash is a 404, not a redirect that repeats the Host header", async () => {
  const app = await buildApp({ db: fakeDb() });

  const response = await app.inject("/health/");

  expect(response.statusCode).toBe(404);
  expect(response.headers.location).toBeUndefined();
});

test("no header gives away what the server is", async () => {
  const response = await (await buildApp({ db: fakeDb() })).inject("/health");

  expect(response.headers.server).toBeUndefined();
  expect(response.headers["x-powered-by"]).toBeUndefined();
});

test("a request with invalid parameters is a 422 that says what is wrong, like the Python services", async () => {
  const app = await buildApp({ db: fakeDb() });
  app.get("/check", {
    schema: {
      querystring: {
        type: "object",
        properties: { limit: { type: "integer", minimum: 1 } },
        required: ["limit"],
      },
    },
    handler: async () => ({}),
  });

  const response = await app.inject("/check?limit=0");

  expect(response.statusCode).toBe(422);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  const body = response.json();
  expect(body).toMatchObject({
    type: "about:blank",
    title: "Unprocessable Entity",
    status: 422,
    detail: "The request has invalid or missing parameters.",
  });
  expect(body.errors).toEqual([
    { loc: ["query", "limit"], msg: expect.any(String), type: expect.any(String) },
  ]);
});

test("a missing parameter is reported with its name", async () => {
  const app = await buildApp({ db: fakeDb() });
  app.get("/check", {
    schema: {
      querystring: { type: "object", properties: { pollutant: { type: "string" } }, required: ["pollutant"] },
    },
    handler: async () => ({}),
  });

  const response = await app.inject("/check");

  expect(response.statusCode).toBe(422);
  expect(response.json().errors[0].loc).toEqual(["query", "pollutant"]);
});

test("a route that fails is a 500 with a fixed text, and the reason goes to the log only", async () => {
  const sink = logSink();
  const app = await buildApp({ db: fakeDb(), logStream: sink.stream, logLevel: "info" });
  app.get("/boom", async () => {
    throw new Error("secret detail of the failure");
  });

  const response = await app.inject("/boom");

  expect(response.statusCode).toBe(500);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.body).not.toContain("secret detail");
  expect(response.json().detail).toBe("The service failed to answer.");
  const failure = sink.records().find((r) => r.level === "ERROR");
  expect(failure).toMatchObject({ logger: "air_quality_service", message: "request failed" });
  expect(String(failure?.exception)).toContain("secret detail of the failure");
});

test("a URL that cannot be read is a problem document, not the text of the framework", async () => {
  const app = await buildApp({ db: fakeDb() });

  const response = await app.inject("/%zz");

  expect(response.statusCode).toBe(400);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json()).toEqual({
    type: "about:blank",
    title: "Bad Request",
    status: 400,
    detail: "Bad Request",
  });
  expect(response.body).not.toContain("FST_ERR");
  expect(response.body).not.toContain("%zz");
});

test("a path parameter that is too long is a problem document that does not repeat it", async () => {
  const app = await buildApp({ db: fakeDb() });
  app.get("/things/:id", async () => ({}));

  const response = await app.inject("/things/" + "a".repeat(200));

  expect(response.statusCode).toBeGreaterThanOrEqual(400);
  expect(response.statusCode).toBeLessThan(500);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.body).not.toContain("aaaaaaaaaa");
  expect(response.body).not.toContain("FST_ERR");
});
