import { expect, test } from "vitest";
import { buildApp } from "../src/app.ts";
import { dbTest } from "./database.ts";
import { brokenDb, scriptedDb } from "./helpers.ts";
import { addGuideline, addHourlyRun, addReadings, addStation } from "./seed.ts";

type Exposure = {
  attribution: string;
  unit: { code: string; name: string; level: string };
  pollutant: string;
  year: number;
  measured: boolean;
  reason: string | null;
  stations: number | null;
  stations_total: number | null;
  mean_ugm3: number | null;
  guideline_ugm3: number | null;
  who_ratio: number | null;
  hours: number | null;
  coverage: number | null;
  coverage_ok: boolean | null;
};

const MUNICIPALITY = "98001"; // the municipality that the test stations are in (tests/seed.ts)
const HOURS_2026 = 8760;

async function exposureOf(db: Parameters<typeof buildApp>[0]["db"], code = MUNICIPALITY, query = "pollutant=T_X&year=2026") {
  const app = await buildApp({ db });
  const response = await app.inject(`/units/${code}/exposure?${query}`);
  expect(response.statusCode).toBe(200);
  return response.json() as Exposure;
}

// --- a municipality with stations ---------------------------------------------------------------

dbTest("the mean of every hourly value of the stations of the municipality, over the annual guideline", async ({ db }) => {
  await addGuideline(db, "T_X", "annual", 10);
  const a = await addStation(db, { code: "T_A" });
  const b = await addStation(db, { code: "T_B" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-03-01T00:00:00Z", value: 10 },
    { ts: "2026-03-01T01:00:00Z", value: 20 },
  ]);
  await addReadings(db, b, "T_X", [{ ts: "2026-03-01T00:00:00Z", value: 30 }]);

  const body = await exposureOf(db);

  expect(body).toMatchObject({
    unit: { code: "98001", name: "Testville", level: "municipality" },
    pollutant: "T_X",
    year: 2026,
    measured: true,
    reason: null,
    stations: 2,
    stations_total: 2,
    mean_ugm3: 20, // (10 + 20 + 30) / 3 values, as unit_indicator does
    guideline_ugm3: 10,
    who_ratio: 2,
  });
  expect(body.attribution).toContain("CC BY 4.0");
});

dbTest("two stations at the same hour are one hour of coverage, not two", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  const b = await addStation(db, { code: "T_B" });
  await addReadings(db, a, "T_X", [{ ts: "2026-03-01T00:00:00Z", value: 1 }]);
  await addReadings(db, b, "T_X", [
    { ts: "2026-03-01T00:00:00Z", value: 1 },
    { ts: "2026-03-01T01:00:00Z", value: 1 },
  ]);

  const body = await exposureOf(db);

  expect(body.hours).toBe(2);
  expect(body.coverage).toBe(Math.round((2 / HOURS_2026) * 10_000) / 10_000);
});

dbTest("the coverage is the share of the hours of the year that have a value, and 75 % is enough", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addHourlyRun(db, a, "T_X", "2026-01-01T00:00:00Z", 6570, 5); // exactly 75 % of 8760

  const body = await exposureOf(db);

  expect(body).toMatchObject({ hours: 6570, coverage: 0.75, coverage_ok: true });
});

dbTest("one hour less than 75 % is not enough", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addHourlyRun(db, a, "T_X", "2026-01-01T00:00:00Z", 6569, 5);

  const body = await exposureOf(db);

  // It shows 0.7499, never 0.75: what is shown and whether it is enough say the same.
  expect(body).toMatchObject({ hours: 6569, coverage: 0.7499, coverage_ok: false });
});

dbTest("each value is converted from its own unit, and a unit that is not known is left out", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-03-01T00:00:00Z", value: 1, unit: "mg/m3" }, // 1000
    { ts: "2026-03-01T01:00:00Z", value: 3000, unit: "µg/m3" },
    { ts: "2026-03-01T02:00:00Z", value: 5_000_000, unit: "ng/m3" }, // 5000
    { ts: "2026-03-01T03:00:00Z", value: 9999, unit: "furlongs" },
  ]);

  const body = await exposureOf(db);

  expect(body).toMatchObject({ mean_ugm3: 3000, hours: 3 });
});

dbTest("only the hourly values of the pollutant and only the stations of the municipality", async ({ db }) => {
  const mine = await addStation(db, { code: "T_A", municipality: "98001" });
  const other = await addStation(db, { code: "T_B", municipality: "98002" });
  await addReadings(db, mine, "T_X", [
    { ts: "2026-03-01T00:00:00Z", value: 10 },
    { ts: "2026-03-01T00:00:00Z", value: 999, period: "8h" },
  ]);
  await addReadings(db, mine, "T_Y", [{ ts: "2026-03-01T00:00:00Z", value: 555 }]);
  await addReadings(db, other, "T_X", [{ ts: "2026-03-01T00:00:00Z", value: 777 }]);

  const body = await exposureOf(db);

  expect(body).toMatchObject({ mean_ugm3: 10, stations: 1, stations_total: 1, hours: 1 });
});

dbTest("the same ratio as the view of impact indicators, which the map uses", async ({ db }) => {
  await addGuideline(db, "T_X", "annual", 8);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-03-01T00:00:00Z", value: 12 },
    { ts: "2026-03-01T01:00:00Z", value: 20 },
    { ts: "2026-03-01T02:00:00Z", value: 7, unit: "mg/m3" },
  ]);
  await db.query("REFRESH MATERIALIZED VIEW core.unit_indicator");
  const { rows } = await db.query<{ who_ratio: string }>(
    "SELECT who_ratio FROM core.unit_indicator WHERE municipality_code = '98001' AND pollutant_code = 'T_X' AND year = 2026",
  );

  const body = await exposureOf(db);

  expect(body.who_ratio).toBe(Math.round(Number(rows[0].who_ratio) * 10_000) / 10_000);
});

dbTest("without an annual guideline there is a mean and no ratio", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25); // the 24-hour guideline is not the annual one
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [{ ts: "2026-03-01T00:00:00Z", value: 10 }]);

  const body = await exposureOf(db);

  expect(body).toMatchObject({ measured: true, mean_ugm3: 10, guideline_ugm3: null, who_ratio: null });
});

// --- not measured: nothing is invented ----------------------------------------------------------

dbTest("a municipality with no station is not measured", async ({ db }) => {
  await addStation(db, { code: "T_A", municipality: "98002" }); // makes the district 9801 and the territory 98
  await db.query("INSERT INTO core.municipality (ine_code, district_code, name, area_km2) VALUES ('98003', '9801', 'Emptyville', 5)");

  const body = await exposureOf(db, "98003");

  expect(body).toMatchObject({
    unit: { code: "98003", name: "Emptyville", level: "municipality" },
    measured: false,
    reason: "no_station",
    stations: 0,
    stations_total: 0,
    mean_ugm3: null,
    who_ratio: null,
    hours: null,
    coverage: null,
    coverage_ok: null,
  });
});

dbTest("a district and a territory exist but are not measured yet: how to add them up is still open", async ({ db }) => {
  await addStation(db, { code: "T_A" });

  const district = await exposureOf(db, "9801");
  const territory = await exposureOf(db, "98");

  expect(district).toMatchObject({ unit: { code: "9801", name: "Test", level: "district" }, measured: false, reason: "level_not_supported" });
  expect(territory).toMatchObject({ unit: { code: "98", name: "Test", level: "territory" }, measured: false, reason: "level_not_supported" });
});

// --- what does not need a database: the contract ----------------------------------------------

const UNIT = { name: "Bilbao" };
const DATA = { mean_ugm3: "21.1234567", hours: "6570", stations: "3", stations_total: "4" };
const GUIDELINE = { value_ugm3: "10.000" };

async function ask(answers: unknown[][], path: string) {
  const db = scriptedDb(answers);
  const app = await buildApp({ db });
  return { response: await app.inject(path), db };
}

const GOOD = "pollutant=NO2&year=2026";

test("a unit that does not exist is a 404 problem document, and nothing else is asked", async () => {
  const { response, db } = await ask([[]], `/units/48999/exposure?${GOOD}`);

  expect(response.statusCode).toBe(404);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json().detail).toBe("Unit 48999 not found.");
  expect(db.asked).toHaveLength(1);
});

test("a district or a territory is not measured and the data is not asked for", async () => {
  const { response, db } = await ask([[UNIT]], `/units/4801/exposure?${GOOD}`);

  expect(response.json()).toMatchObject({ unit: { level: "district" }, measured: false, reason: "level_not_supported" });
  expect(db.asked).toHaveLength(1);
});

test.each([
  ["a code of one digit", "1"],
  ["a code of three digits", "480"],
  ["a code of six digits", "480200"],
  ["a code with letters", "48a20"],
  ["a code with a hex prefix", "0x1234"],
])("%s is a 422 about the path, and nothing is asked of the database", async (_name, code) => {
  const { response, db } = await ask([], `/units/${code}/exposure?${GOOD}`);

  expect(response.statusCode).toBe(422);
  expect(response.json().errors[0].loc).toEqual(["path", "code"]);
  expect(db.asked).toEqual([]);
});

test.each([
  ["a missing pollutant", "year=2026", "pollutant"],
  ["a lower case pollutant", "pollutant=no2&year=2026", "pollutant"],
  ["a missing year", "pollutant=NO2", "year"],
  ["a year that is not a number", "pollutant=NO2&year=last", "year"],
  ["a year with decimals", "pollutant=NO2&year=2026.5", "year"],
  ["a year in hexadecimal, which would be 2024", "pollutant=NO2&year=0x7e8", "year"],
  ["a year with a sign", "pollutant=NO2&year=%2B2026", "year"],
  ["a year in exponent form, which would be 2000", "pollutant=NO2&year=2e3", "year"],
  ["a year with a zero in front", "pollutant=NO2&year=02026", "year"],
  ["a year before 1900", "pollutant=NO2&year=1899", "year"],
  ["a year after 2100", "pollutant=NO2&year=2101", "year"],
])("%s is a 422 that names the parameter", async (_name, query, name) => {
  const { response, db } = await ask([], `/units/48020/exposure?${query}`);

  expect(response.statusCode).toBe(422);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json().errors[0].loc).toEqual(["query", name]);
  expect(db.asked).toEqual([]);
});

test("a database that fails is a 500 with a fixed text", async () => {
  const app = await buildApp({ db: brokenDb() });

  const response = await app.inject(`/units/48020/exposure?${GOOD}`);

  expect(response.statusCode).toBe(500);
  expect(response.body).not.toContain("reader_secret");
});

