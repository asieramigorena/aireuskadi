import { expect, test } from "vitest";
import { buildApp } from "../src/app.js";
import { fakeDb } from "./helpers.js";

test("the gateway can read the description of the routes at /openapi.json", async () => {
  const app = await buildApp({ db: fakeDb() });
  app.get("/example", { schema: { response: { 200: { type: "object" } } }, handler: async () => ({}) });

  const response = await app.inject("/openapi.json");

  expect(response.statusCode).toBe(200);
  const document = response.json();
  expect(document.openapi).toMatch(/^3\./);
  expect(document.info.title).toBe("AirEuskadi Air Quality Service");
  expect(Object.keys(document.paths)).toEqual(["/example"]);
});

test("the check of the compose and the description itself are not in the description", async () => {
  const app = await buildApp({ db: fakeDb() });
  const document = (await app.inject("/openapi.json")).json();

  expect(document.paths).toEqual({});
});
