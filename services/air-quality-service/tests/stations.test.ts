import { expect, test } from "vitest";
import { buildApp } from "../src/app.ts";
import { dbTest } from "./database.ts";
import { brokenDb, fakeDb } from "./helpers.ts";
import { addMunicipality, addStation } from "./seed.ts";

type Collection = {
  type: string;
  attribution: string;
  features: { type: string; geometry: { type: string; coordinates: number[] } | null; properties: Record<string, unknown> }[];
};

async function stationsOf(db: Parameters<typeof buildApp>[0]["db"]) {
  const app = await buildApp({ db });
  const response = await app.inject("/stations");
  expect(response.statusCode).toBe(200);
  const body = response.json() as Collection;
  // Only the stations of the test: the database may hold others.
  return { ...body, features: body.features.filter((f) => String(f.properties.code).startsWith("T_")) };
}

dbTest("the stations are GeoJSON points with their municipality, in the order of their code", async ({ db }) => {
  await addStation(db, { code: "T_B", name: "Second", areaType: "suburban", at: [-1.98, 43.31] });
  const first = await addStation(db, { code: "T_A", name: "First", areaType: "urban", at: [-2.935, 43.263] });

  const body = await stationsOf(db);

  expect(body.type).toBe("FeatureCollection");
  expect(body.features.map((f) => f.properties.code)).toEqual(["T_A", "T_B"]);
  expect(body.features[0]).toEqual({
    type: "Feature",
    geometry: { type: "Point", coordinates: [-2.935, 43.263] },
    properties: {
      id: first,
      code: "T_A",
      name: "First",
      area_type: "urban",
      municipality_code: "98001",
      municipality_name: "Testville",
    },
  });
});

dbTest("a station without a position is listed with a null geometry, not left out or placed at 0,0", async ({ db }) => {
  await addStation(db, { code: "T_A", at: null });

  const body = await stationsOf(db);

  expect(body.features).toHaveLength(1);
  expect(body.features[0].geometry).toBeNull();
});

const ROW = {
  id: 7,
  code: "100",
  name: "Station",
  area_type: "urban",
  municipality_code: "48020",
  municipality_name: "Bilbao",
  geometry: { type: "Point", coordinates: [-2.9, 43.2] },
};

async function answerFor(rows: unknown[]) {
  const app = await buildApp({ db: fakeDb(rows) });
  return (await app.inject("/stations")).json() as Collection;
}

// These do not need a database, so the CI runs them: the shape of the answer is the contract.
test("the response carries the credit of the source", async () => {
  const body = await answerFor([]);

  expect(body.attribution).toContain("CC BY 4.0");
  expect(body.attribution).toContain("Gobierno Vasco");
});

test("a row becomes a feature with exactly the properties of the contract", async () => {
  const body = await answerFor([ROW]);

  expect(body.features).toEqual([
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-2.9, 43.2] },
      properties: {
        id: 7,
        code: "100",
        name: "Station",
        area_type: "urban",
        municipality_code: "48020",
        municipality_name: "Bilbao",
      },
    },
  ]);
});

test("without stations the answer is an empty list, not an error", async () => {
  const app = await buildApp({ db: fakeDb([]) });

  const response = await app.inject("/stations");

  expect(response.statusCode).toBe(200);
  expect((response.json() as Collection).features).toEqual([]);
});

test("a database that fails is a 500 with a fixed text", async () => {
  const app = await buildApp({ db: brokenDb() });

  const response = await app.inject("/stations");

  expect(response.statusCode).toBe(500);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.body).not.toContain("reader_secret");
});

