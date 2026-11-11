import { expect, test } from "vitest";
import { buildApp } from "../src/app.js";
import { dbTest } from "./database.js";
import { brokenDb, scriptedDb } from "./helpers.js";
import { addReadings, addStation, hourly } from "./seed.js";

type Series = {
  attribution: string;
  station: { id: number; code: string; name: string };
  pollutant: string;
  interval: string;
  unit: string;
  from: string;
  to: string;
  points: { ts: string; value: number; hours?: number; coverage_ok?: boolean }[];
};

const FROM = "2026-01-10T00:00:00Z";
const TO = "2026-01-11T00:00:00Z";

function url(id: number | string, query: Record<string, string>) {
  return `/stations/${id}/measurements?${new URLSearchParams(query)}`;
}

async function seriesOf(db: Parameters<typeof buildApp>[0]["db"], id: number, query: Record<string, string>) {
  const app = await buildApp({ db });
  const response = await app.inject(url(id, { pollutant: "T_X", from: FROM, to: TO, ...query }));
  expect(response.statusCode).toBe(200);
  return response.json() as Series;
}

// --- the hourly series --------------------------------------------------------------------------

dbTest("the hourly values of the range, in time order, with the station and what was asked", async ({ db }) => {
  const id = await addStation(db, { code: "T_A", name: "First" });
  await addReadings(db, id, "T_X", [
    { ts: "2026-01-10T02:00:00Z", value: 30 },
    { ts: "2026-01-10T01:00:00Z", value: 20 },
    { ts: "2026-01-10T00:00:00Z", value: 10 },
  ]);

  const body = await seriesOf(db, id, {});

  expect(body).toMatchObject({
    station: { id, code: "T_A", name: "First" },
    pollutant: "T_X",
    interval: "hour",
    unit: "µg/m3",
    from: "2026-01-10T00:00:00.000Z",
    to: "2026-01-11T00:00:00.000Z",
  });
  expect(body.points).toEqual([
    { ts: "2026-01-10T00:00:00.000Z", value: 10 },
    { ts: "2026-01-10T01:00:00.000Z", value: 20 },
    { ts: "2026-01-10T02:00:00.000Z", value: 30 },
  ]);
  expect(body.attribution).toContain("CC BY 4.0");
});

dbTest("the range includes `from` and leaves out `to`", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [
    { ts: "2026-01-09T23:00:00Z", value: 1 },
    { ts: "2026-01-10T00:00:00Z", value: 2 },
    { ts: "2026-01-10T23:00:00Z", value: 3 },
    { ts: "2026-01-11T00:00:00Z", value: 4 },
  ]);

  const body = await seriesOf(db, id, {});

  expect(body.points.map((p) => p.value)).toEqual([2, 3]);
});

dbTest("only the values of that station and that pollutant, and only the hourly ones", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  const b = await addStation(db, { code: "T_B" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-01-10T01:00:00Z", value: 1 },
    { ts: "2026-01-10T01:00:00Z", value: 99, period: "8h" },
  ]);
  await addReadings(db, a, "T_Y", [{ ts: "2026-01-10T01:00:00Z", value: 50 }]);
  await addReadings(db, b, "T_X", [{ ts: "2026-01-10T01:00:00Z", value: 60 }]);

  const body = await seriesOf(db, a, {});

  expect(body.points.map((p) => p.value)).toEqual([1]);
});

dbTest("every value is in ug/m3 whatever unit it was published in, and an unknown unit is left out", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [
    { ts: "2026-01-10T00:00:00Z", value: 0.5, unit: "mg/m3" },
    { ts: "2026-01-10T01:00:00Z", value: 20_000, unit: "ng/m3" },
    { ts: "2026-01-10T02:00:00Z", value: 7, unit: "µg/m3" },
    { ts: "2026-01-10T03:00:00Z", value: 9999, unit: "furlongs" },
  ]);

  const body = await seriesOf(db, id, {});

  expect(body.points.map((p) => p.value)).toEqual([500, 20, 7]);
});

dbTest("a range without values is an empty list, not an error", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });

  const body = await seriesOf(db, id, {});

  expect(body.points).toEqual([]);
});

// --- the daily series -------------------------------------------------------------------------

dbTest("a day is a calendar day in UTC: its mean, how many hours it has and whether it is enough", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [
    ...hourly("2026-01-11T09:00:00.000Z", 10, 40), // 00:00 to 09:00 of the 11th: 10 hours (written first)
    ...hourly("2026-01-10T23:00:00.000Z", 24, 10), // the whole of the 10th
  ]);

  const body = await seriesOf(db, id, { interval: "day", to: "2026-01-12T00:00:00Z" });

  expect(body.interval).toBe("day");
  expect(body.points).toEqual([
    { ts: "2026-01-10T00:00:00.000Z", value: 10, hours: 24, coverage_ok: true },
    { ts: "2026-01-11T00:00:00.000Z", value: 40, hours: 10, coverage_ok: false },
  ]);
});

dbTest("18 hours are enough for a day, 17 are not", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [
    ...hourly("2026-01-10T17:00:00.000Z", 18, 10),
    ...hourly("2026-01-11T16:00:00.000Z", 17, 10),
  ]);

  const body = await seriesOf(db, id, { interval: "day", to: "2026-01-12T00:00:00Z" });

  expect(body.points.map((p) => [p.hours, p.coverage_ok])).toEqual([
    [18, true],
    [17, false],
  ]);
});

dbTest("the hour 23:00 UTC belongs to its own day, not to the next", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [{ ts: "2026-01-10T23:00:00Z", value: 5 }]);

  const body = await seriesOf(db, id, { interval: "day", to: "2026-01-12T00:00:00Z" });

  expect(body.points.map((p) => p.ts)).toEqual(["2026-01-10T00:00:00.000Z"]);
});

dbTest("the day is a UTC day even when the time zone of the database session is another one", async ({ db }) => {
  await db.query("SET LOCAL TIME ZONE 'Asia/Tokyo'"); // 9 hours ahead: 23:00 UTC would be 08:00 of the next day
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [{ ts: "2026-01-10T23:00:00Z", value: 5 }]);

  const body = await seriesOf(db, id, { interval: "day", to: "2026-01-12T00:00:00Z" });

  expect(body.points.map((p) => p.ts)).toEqual(["2026-01-10T00:00:00.000Z"]);
});

dbTest("the mean of a day converts each value with its own unit and counts only the known ones", async ({ db }) => {
  const id = await addStation(db, { code: "T_A" });
  await addReadings(db, id, "T_X", [
    { ts: "2026-01-10T00:00:00Z", value: 1, unit: "mg/m3" },
    { ts: "2026-01-10T01:00:00Z", value: 3000, unit: "µg/m3" },
    { ts: "2026-01-10T02:00:00Z", value: 9999, unit: "furlongs" },
  ]);

  const body = await seriesOf(db, id, { interval: "day" });

  expect(body.points).toEqual([{ ts: "2026-01-10T00:00:00.000Z", value: 2000, hours: 2, coverage_ok: false }]);
});

// --- what does not need a database: the contract ----------------------------------------------

const STATION = { id: 7, code: "100", name: "Station" };
const GOOD = { pollutant: "NO2", from: FROM, to: TO };

async function ask(answers: unknown[][], path: string) {
  const db = scriptedDb(answers);
  const app = await buildApp({ db });
  return { response: await app.inject(path), db };
}

test("a station that does not exist is a 404 problem document", async () => {
  const { response, db } = await ask([[]], url(404, GOOD));

  expect(response.statusCode).toBe(404);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json().detail).toBe("Station 404 not found.");
  expect(db.asked).toHaveLength(1); // it did not go on to ask for values
});

test("a station that exists but has no values for the range is an empty list", async () => {
  const { response } = await ask([[STATION], []], url(7, GOOD));

  expect(response.statusCode).toBe(200);
  expect((response.json() as Series).points).toEqual([]);
});

test("the numbers that the database gives as text are numbers, the times are ISO, values have three decimals", async () => {
  const hours = [{ ts: new Date("2026-01-10T00:00:00Z"), ugm3: "12.34567" }];
  const days = [{ day: new Date("2026-01-10T00:00:00Z"), ugm3: "33.3333333333", hours: "24" }];

  const hourlyBody = (await ask([[STATION], hours], url(7, GOOD))).response.json() as Series;
  const dailyBody = (await ask([[STATION], days], url(7, { ...GOOD, interval: "day" }))).response.json() as Series;

  expect(hourlyBody.points).toEqual([{ ts: "2026-01-10T00:00:00.000Z", value: 12.346 }]);
  expect(dailyBody.points).toEqual([{ ts: "2026-01-10T00:00:00.000Z", value: 33.333, hours: 24, coverage_ok: true }]);
});

test("the parameters go to the database as parameters, never written into the query", async () => {
  const { db } = await ask([[STATION], []], url(7, GOOD));

  expect(db.asked).toHaveLength(2);
  expect(db.asked[0].params).toEqual([7]);
  expect(db.asked[1].params).toEqual([7, "NO2", new Date(FROM), new Date(TO)]);
  for (const { text } of db.asked) expect(text).not.toMatch(/NO2|2026/);
});

const day = 86_400_000;
const at = (ms: number) => new Date(Date.parse(FROM) + ms).toISOString();

test.each([
  ["a missing pollutant", { from: FROM, to: TO }, "pollutant"],
  ["a lower case pollutant", { ...GOOD, pollutant: "no2" }, "pollutant"],
  ["a missing from", { pollutant: "NO2", to: TO }, "from"],
  ["a missing to", { pollutant: "NO2", from: FROM }, "to"],
  ["a from that is not a date", { ...GOOD, from: "yesterday" }, "from"],
  ["a to that is not a date", { ...GOOD, to: "2026-13-45T00:00:00Z" }, "to"],
  ["a date with no time zone", { ...GOOD, from: "2026-01-10T00:00:00" }, "from"],
  ["an interval that does not exist", { ...GOOD, interval: "week" }, "interval"],
])("%s is a 422 that names the parameter", async (_name, query, name) => {
  const { response, db } = await ask([], url(7, query as Record<string, string>));

  expect(response.statusCode).toBe(422);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json().errors[0].loc).toEqual(["query", name]);
  expect(db.asked).toEqual([]); // nothing was asked of the database
});

test.each(["abc", "0", "-3", "1.5", "0x10", "007", "1e2", "+7", "7%20", "%207", "99999999999", "1e21"])(
  "the station id %j is a 422 about the path, and nothing is asked of the database",
  async (id) => {
    const { response, db } = await ask([], url(id, GOOD));

    expect(response.statusCode).toBe(422);
    expect(response.json().errors[0].loc).toEqual(["path", "id"]);
    expect(db.asked).toEqual([]);
  },
);

test("an id that is a number but is beyond the integer of the database is a station that does not exist", async () => {
  const { response, db } = await ask([], url("2147483648", GOOD));

  expect(response.statusCode).toBe(404);
  expect(response.json().detail).toBe("Station 2147483648 not found.");
  expect(db.asked).toEqual([]); // PostgreSQL would have refused the number: that was a 500
});

test("the largest id of the database is looked up like any other", async () => {
  const { response, db } = await ask([[]], url("2147483647", GOOD));

  expect(response.statusCode).toBe(404);
  expect(db.asked).toHaveLength(1);
});

test.each(["from", "to"])("a leap second in `%s` is a 422, not a 500: JavaScript cannot read it", async (name) => {
  const query = { ...GOOD, from: "2026-12-30T00:00:00Z", to: "2026-12-31T00:00:00Z", [name]: "2026-12-31T23:59:60Z" };

  const { response, db } = await ask([[STATION], []], url(7, query));

  expect(response.statusCode).toBe(422);
  expect(response.json().errors[0].loc).toEqual(["query", name]);
  expect(db.asked).toEqual([]);
});

test.each([
  ["hour", at(0), at(31 * day), 200],
  ["hour", at(0), at(31 * day + 3_600_000), 422],
  ["day", at(0), at(366 * day), 200],
  ["day", at(0), at(366 * day + 3_600_000), 422],
])("a %s series from %s to %s answers %i", async (interval, from, to, status) => {
  const { response } = await ask([[STATION], []], url(7, { ...GOOD, interval, from, to }));

  expect(response.statusCode).toBe(status);
  if (status === 422) {
    expect(response.json().errors[0].loc).toEqual(["query", "to"]);
    expect(response.json().errors[0].msg).toContain(interval === "hour" ? "31 days" : "366 days");
  }
});

test.each([
  ["equal", FROM],
  ["before", "2026-01-09T00:00:00Z"],
])("a `to` that is %s the `from` is a 422", async (_name, to) => {
  const { response } = await ask([], url(7, { ...GOOD, to }));

  expect(response.statusCode).toBe(422);
  expect(response.json().errors[0].loc).toEqual(["query", "to"]);
});

test("a database that fails is a 500 with a fixed text", async () => {
  const app = await buildApp({ db: brokenDb() });

  const response = await app.inject(url(7, GOOD));

  expect(response.statusCode).toBe(500);
  expect(response.body).not.toContain("reader_secret");
});

test("the description of the routes has the path parameter, the query ones, and the two problem documents", async () => {
  const app = await buildApp({ db: scriptedDb([]) });

  const document = (await app.inject("/openapi.json")).json();

  const operation = document.paths["/stations/{id}/measurements"].get;
  const parameters = Object.fromEntries(operation.parameters.map((p: { name: string }) => [p.name, p]));
  expect(parameters.id).toMatchObject({ in: "path", required: true });
  for (const name of ["pollutant", "from", "to"]) expect(parameters[name]).toMatchObject({ in: "query", required: true });
  expect(parameters.interval).toMatchObject({ in: "query" });
  expect(parameters.interval.required).not.toBe(true);
  expect(Object.keys(operation.responses["404"].content)).toEqual(["application/problem+json"]);
  expect(Object.keys(operation.responses["422"].content)).toEqual(["application/problem+json"]);
});
