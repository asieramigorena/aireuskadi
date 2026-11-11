import { expect, test } from "vitest";
import { buildApp } from "../src/app.js";
import { brokenDb, fakeDb } from "./helpers.js";

test("the check of the compose answers ok after asking the database for 1", async () => {
  const db = fakeDb([{ "?column?": 1 }]);
  const app = await buildApp({ db });

  const response = await app.inject("/health");

  expect(response.statusCode).toBe(200);
  expect(response.json()).toEqual({ status: "ok" });
  expect(db.asked).toEqual(["SELECT 1"]);
});

test("without a database it answers 503 with a fixed text, never the reason", async () => {
  const app = await buildApp({ db: brokenDb() });

  const response = await app.inject("/health");

  expect(response.statusCode).toBe(503);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.body).not.toContain("reader_secret");
  expect(response.json().detail).toBe("The service is not ready.");
});
