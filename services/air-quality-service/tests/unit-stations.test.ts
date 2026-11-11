import { expect, test } from "vitest";
import { buildApp } from "../src/app.js";
import { dbTest } from "./database.js";
import { brokenDb, scriptedDb } from "./helpers.js";
import { addGuideline, addReadings, addStation, hourly } from "./seed.js";

type Reading = {
  pollutant: string;
  ts: string;
  value: number;
  unit: string;
  who_period: string | null;
  who_guideline_ugm3: number | null;
  who_mean_ugm3: number | null;
  who_samples: number | null;
  who_ratio: number | null;
};
type UnitStations = {
  attribution: string;
  unit: { code: string; name: string; level: string };
  measured: boolean;
  reason: string | null;
  stations: { id: number; code: string; name: string; geometry: unknown; readings: Reading[] }[] | null;
};

const MUNICIPALITY = "98001"; // the municipality that the test stations are in (tests/seed.ts)
const END = "2026-01-15T12:00:00.000Z";

async function stationsOf(db: Parameters<typeof buildApp>[0]["db"], code = MUNICIPALITY) {
  const app = await buildApp({ db });
  const response = await app.inject(`/units/${code}/stations`);
  expect(response.statusCode).toBe(200);
  return response.json() as UnitStations;
}

// --- a municipality with stations ---------------------------------------------------------------

dbTest("each station of the municipality gives its latest value of each pollutant, ordered by code", async ({ db }) => {
  // Made in the opposite order to the one they must come in.
  const b = await addStation(db, { code: "T_B", name: "Second" });
  await addReadings(db, b, "T_X", [{ ts: "2026-01-15T09:00:00Z", value: 8, unit: "mg/m3" }]);
  const a = await addStation(db, { code: "T_A", name: "First" });
  await addReadings(db, a, "T_Y", [
    { ts: "2026-01-15T10:00:00Z", value: 5 },
    { ts: "2026-01-15T11:00:00Z", value: 6 },
  ]);
  await addReadings(db, a, "T_X", [{ ts: END, value: 30 }]);

  const body = await stationsOf(db);

  expect(body).toMatchObject({
    unit: { code: "98001", name: "Testville", level: "municipality" },
    measured: true,
    reason: null,
  });
  expect(body.attribution).toContain("CC BY 4.0");
  expect(body.stations!.map((s) => s.code)).toEqual(["T_A", "T_B"]);
  expect(body.stations![0]).toMatchObject({ id: a, name: "First", geometry: { type: "Point", coordinates: [-2.935, 43.263] } });
  expect(body.stations![0].readings.map((r) => [r.pollutant, r.value, r.ts])).toEqual([
    ["T_X", 30, "2026-01-15T12:00:00.000Z"],
    ["T_Y", 6, "2026-01-15T11:00:00.000Z"],
  ]);
  expect(body.stations![1].readings).toMatchObject([{ pollutant: "T_X", value: 8, unit: "mg/m3" }]);
});

dbTest("the running mean of 8 hours is not the latest hourly value", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-01-15T11:00:00Z", value: 5 },
    { ts: END, value: 99, period: "8h" },
  ]);

  const body = await stationsOf(db);

  expect(body.stations![0].readings).toMatchObject([{ pollutant: "T_X", value: 5, ts: "2026-01-15T11:00:00.000Z" }]);
});

dbTest("the comparison with the WHO guideline is the one of the latest values of the stations", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 15);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 30));
  await addReadings(db, a, "T_Y", [{ ts: END, value: 1 }]);

  const body = await stationsOf(db);

  const [x, y] = body.stations![0].readings;
  expect(x).toMatchObject({ who_period: "24h", who_guideline_ugm3: 15, who_mean_ugm3: 30, who_samples: 24, who_ratio: 2 });
  expect(y).toMatchObject({ who_period: null, who_guideline_ugm3: null, who_mean_ugm3: null, who_samples: null, who_ratio: null });
});

dbTest("a station with fewer than 18 values in the last 24 hours has no ratio", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 15);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 17, 30));

  const body = await stationsOf(db);

  expect(body.stations![0].readings[0]).toMatchObject({ who_samples: 17, who_ratio: null });
});

dbTest("the stations of other municipalities are not listed", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  const other = await addStation(db, { code: "T_OTHER", municipality: "98002" });
  await addReadings(db, a, "T_X", [{ ts: END, value: 1 }]);
  await addReadings(db, other, "T_X", [{ ts: END, value: 2 }]);

  const body = await stationsOf(db);

  expect(body.stations!.map((s) => s.code)).toEqual(["T_A"]);
});

// --- what is not there is said, not invented -----------------------------------------------------

dbTest("a station without values is listed with no readings, and the municipality is not measured", async ({ db }) => {
  await addStation(db, { code: "T_A" });

  const body = await stationsOf(db);

  expect(body.measured).toBe(false);
  expect(body.reason).toBe("no_data");
  expect(body.stations).toMatchObject([{ code: "T_A", readings: [] }]);
});

dbTest("a municipality without stations says so", async ({ db }) => {
  await addStation(db, { code: "T_A", municipality: "98002" });
  const app = await buildApp({ db });
  await db.query(
    "INSERT INTO core.municipality (ine_code, district_code, name, area_km2) VALUES ('98003', '9801', 'Empty', 1) ON CONFLICT DO NOTHING",
  );

  const response = await app.inject("/units/98003/stations");

  expect(response.statusCode).toBe(200);
  expect(response.json()).toMatchObject({
    unit: { code: "98003", name: "Empty", level: "municipality" },
    measured: false,
    reason: "no_station",
    stations: [],
  });
});

dbTest.for([
  ["98", "territory"],
  ["9801", "district"],
])("a %s is not a municipality: no stations are added up for it until it is decided (#33)", async ([code, level], { db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [{ ts: END, value: 1 }]);

  const body = await stationsOf(db, code);

  expect(body).toMatchObject({ unit: { code, level }, measured: false, reason: "level_not_supported", stations: null });
});

dbTest("a code that no unit has is a 404 problem document", async ({ db }) => {
  const app = await buildApp({ db });

  const response = await app.inject("/units/99999/stations");

  expect(response.statusCode).toBe(404);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json().detail).toBe("Unit 99999 not found.");
});

test("the municipality and the pollutants go to the readings query as parameters, never in its text", async () => {
  const db = scriptedDb([[{ name: "Testville" }], [{ id: 1, code: "A", name: "A", geometry: null }], [{ codes: ["NO2", "PM10"] }], []]);
  const app = await buildApp({ db });

  await app.inject("/units/98001/stations");

  const readings = db.asked[3];
  expect(readings.params).toEqual([["NO2", "PM10"], "98001"]);
  expect(readings.text).not.toContain("98001");
});

dbTest("a station without values is listed next to one that has them, and the municipality is measured", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addStation(db, { code: "T_B" });
  await addReadings(db, a, "T_X", [{ ts: END, value: 1 }]);

  const body = await stationsOf(db);

  expect(body).toMatchObject({ measured: true, reason: null });
  expect(body.stations!.map((s) => [s.code, s.readings.length])).toEqual([
    ["T_A", 1],
    ["T_B", 0],
  ]);
});

// --- the request --------------------------------------------------------------------------------

test.for(["123", "1", "abcde", "0x10", "+9800", "98001%20", "9800%0A", "123456", "%EF%BC%99%EF%BC%98"])(
  "%s is not a code of a unit: 422, and the database is not asked",
  async (code) => {
    const asked: string[] = [];
    const app = await buildApp({
      db: {
        async query(text: string) {
          asked.push(text);
          return { rows: [] } as never;
        },
      },
    });

    const response = await app.inject(`/units/${code}/stations`);

    expect(response.statusCode).toBe(422);
    expect(response.headers["content-type"]).toContain("application/problem+json");
    expect(asked).toEqual([]);
  },
);

test("a database that fails is a 500 with a fixed text that says nothing of the reason", async () => {
  const app = await buildApp({ db: brokenDb() });

  const response = await app.inject("/units/98001/stations");

  expect(response.statusCode).toBe(500);
  expect(response.body).not.toContain("reader_secret");
  expect(response.body).not.toContain("password");
});

test("the route is in the OpenAPI document", async () => {
  const app = await buildApp({ db: brokenDb() });

  const paths = Object.keys(((await app.inject("/openapi.json")).json() as { paths: object }).paths);

  expect(paths).toContain("/units/{code}/stations");
});
