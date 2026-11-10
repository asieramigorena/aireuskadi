import { expect, test } from "vitest";
import { buildApp } from "../src/app.js";
import { dbTest } from "./database.js";
import { brokenDb, fakeDb } from "./helpers.js";
import { addGuideline, addReadings, addStation, hourly } from "./seed.js";

type Latest = {
  type: string;
  attribution: string;
  pollutant: string;
  features: { type: string; geometry: unknown; properties: Record<string, unknown> }[];
};

const END = "2026-01-15T12:00:00.000Z";

async function latestOf(db: Parameters<typeof buildApp>[0]["db"], pollutant: string) {
  const app = await buildApp({ db });
  const response = await app.inject(`/stations/latest?pollutant=${pollutant}`);
  expect(response.statusCode).toBe(200);
  const body = response.json() as Latest;
  // Only the stations of the test: the database may hold others.
  return { ...body, features: body.features.filter((f) => String(f.properties.code).startsWith("T_")) };
}

const propertiesOf = (body: Latest, code: string) => body.features.find((f) => f.properties.code === code)?.properties;

// --- the latest hourly value of each station ---------------------------------------------------

dbTest("each station gives its most recent hourly value, with its time and unit", async ({ db }) => {
  const a = await addStation(db, { code: "T_A", name: "First" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-01-15T10:00:00Z", value: 10 },
    { ts: "2026-01-15T12:00:00Z", value: 30 },
    { ts: "2026-01-15T11:00:00Z", value: 20 },
  ]);

  const body = await latestOf(db, "T_X");

  expect(body.type).toBe("FeatureCollection");
  expect(body.pollutant).toBe("T_X");
  expect(body.features).toHaveLength(1);
  expect(body.features[0].geometry).toEqual({ type: "Point", coordinates: [-2.935, 43.263] });
  expect(body.features[0].properties).toMatchObject({
    id: a,
    code: "T_A",
    name: "First",
    municipality_code: "98001",
    ts: "2026-01-15T12:00:00.000Z",
    value: 30,
    unit: "µg/m3",
  });
});

dbTest("only the stations that measure the pollutant are listed", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  const b = await addStation(db, { code: "T_B" });
  await addReadings(db, a, "T_X", [{ ts: END, value: 1 }]);
  await addReadings(db, b, "T_Y", [{ ts: END, value: 2 }]);

  const body = await latestOf(db, "T_X");

  expect(body.features.map((f) => f.properties.code)).toEqual(["T_A"]);
});

dbTest("the running mean of 8 hours is not the hourly value", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-01-15T11:00:00Z", value: 5 },
    { ts: END, value: 99, period: "8h" },
  ]);

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ value: 5, ts: "2026-01-15T11:00:00.000Z" });
});

dbTest("a station whose latest value is old is still listed with its time", async ({ db }) => {
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [{ ts: "2025-06-01T00:00:00Z", value: 7 }]);

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ ts: "2025-06-01T00:00:00.000Z", value: 7 });
});

dbTest("the stations come in the order of their code", async ({ db }) => {
  for (const code of ["T_C", "T_A", "T_B"]) {
    const id = await addStation(db, { code });
    await addReadings(db, id, "T_X", [{ ts: END, value: 1 }]);
  }

  const body = await latestOf(db, "T_X");

  expect(body.features.map((f) => f.properties.code)).toEqual(["T_A", "T_B", "T_C"]);
});

// --- the comparison with the WHO guideline of its own period -----------------------------------

dbTest("a 24-hour guideline is compared with the mean of the last 24 hourly values", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 50));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({
    who_period: "24h",
    who_guideline_ugm3: 25,
    who_mean_ugm3: 50,
    who_samples: 24,
    who_ratio: 2,
  });
});

dbTest("values older than 24 hours before the latest one are not in the mean", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [...hourly("2026-01-14T00:00:00.000Z", 30, 1000), ...hourly(END, 24, 50)]);

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_mean_ugm3: 50, who_samples: 24, who_ratio: 2 });
});

dbTest("with fewer than 18 values in the last 24 hours there is no ratio, and it says how many there were", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 17, 50));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_period: "24h", who_samples: 17, who_ratio: null });
});

dbTest("with exactly 18 values the ratio is computed", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 18, 50));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_samples: 18, who_ratio: 2 });
});

dbTest("a value in mg/m3 is converted before it is compared, and the value itself keeps its unit", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 4000);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 2, "mg/m3"));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ value: 2, unit: "mg/m3", who_mean_ugm3: 2000, who_ratio: 0.5 });
});

dbTest("a value in a unit that is not known is left out of the mean instead of guessed", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [...hourly(END, 20, 50), { ts: "2026-01-15T13:00:00.000Z", value: 9999, unit: "furlongs" }]);

  const body = await latestOf(db, "T_X");

  // The latest value is the one in furlongs, but only values in a known unit make a mean.
  expect(propertiesOf(body, "T_A")).toMatchObject({ who_mean_ugm3: 50, who_samples: 20 });
});

dbTest("a value exactly 24 hours before the latest one is out of the mean, and one 23 hours before is in", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: "2026-01-14T12:00:00Z", value: 1000 }, // 24 hours before 12:00: out
    ...hourly("2026-01-15T12:00:00.000Z", 24, 50), // from 13:00 the day before: 24 values
  ]);

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_samples: 24, who_mean_ugm3: 50 });
});

dbTest("a value in ng/m3 is converted too", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 50_000, "ng/m3"));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_mean_ugm3: 50, who_ratio: 2 });
});

dbTest("an 8-hour mean in a unit that is not known is not used", async ({ db }) => {
  await addGuideline(db, "T_X", "8h", 100);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: END, value: 50 },
    { ts: "2026-01-15T11:00:00Z", value: 120, period: "8h" },
    { ts: END, value: 9999, period: "8h", unit: "furlongs" },
  ]);

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_mean_ugm3: 120, who_ratio: 1.2 });
});

dbTest("an 8-hour guideline is compared with the latest running mean of 8 hours, not with the hourly value", async ({ db }) => {
  await addGuideline(db, "T_X", "8h", 100);
  await addGuideline(db, "T_X", "peak_season", 60);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", [
    { ts: END, value: 400 },
    { ts: "2026-01-15T11:00:00Z", value: 150, period: "8h" },
    { ts: END, value: 120, period: "8h" },
  ]);

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({
    value: 400,
    who_period: "8h",
    who_guideline_ugm3: 100,
    who_mean_ugm3: 120,
    who_ratio: 1.2,
  });
});

dbTest("with both a 24-hour and an 8-hour guideline, the 24-hour one is used", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 25);
  await addGuideline(db, "T_X", "8h", 100);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 50));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_period: "24h" });
});

dbTest("the most recent edition of the guideline is the one used", async ({ db }) => {
  await addGuideline(db, "T_X", "24h", 50, 2005);
  await addGuideline(db, "T_X", "24h", 25, 2021);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 50));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({ who_guideline_ugm3: 25, who_ratio: 2 });
});

dbTest("a pollutant that has only an annual guideline is not compared: nothing is invented", async ({ db }) => {
  await addGuideline(db, "T_X", "annual", 10);
  const a = await addStation(db, { code: "T_A" });
  await addReadings(db, a, "T_X", hourly(END, 24, 50));

  const body = await latestOf(db, "T_X");

  expect(propertiesOf(body, "T_A")).toMatchObject({
    value: 50,
    who_period: null,
    who_guideline_ugm3: null,
    who_mean_ugm3: null,
    who_samples: null,
    who_ratio: null,
  });
});

// --- what does not need a database: the contract ----------------------------------------------

const ROW = {
  id: 7,
  code: "100",
  name: "Station",
  municipality_code: "48020",
  geometry: { type: "Point", coordinates: [-2.9, 43.2] },
  ts: new Date("2026-01-15T12:00:00Z"),
  value: "30.500",
  unit: "µg/m3",
  who_period: "24h",
  who_guideline_ugm3: "25.000",
  who_mean_ugm3: "50.0000000000000000",
  who_samples: "24",
};

async function answerFor(rows: unknown[], query = "pollutant=NO2") {
  const app = await buildApp({ db: fakeDb(rows) });
  return app.inject(`/stations/latest?${query}`);
}

test("the numbers that the database gives as text are numbers in the answer, and the time is ISO", async () => {
  const body = (await answerFor([ROW])).json() as Latest;

  expect(body.features[0].properties).toEqual({
    id: 7,
    code: "100",
    name: "Station",
    municipality_code: "48020",
    ts: "2026-01-15T12:00:00.000Z",
    value: 30.5,
    unit: "µg/m3",
    who_period: "24h",
    who_guideline_ugm3: 25,
    who_mean_ugm3: 50,
    who_samples: 24,
    who_ratio: 2,
  });
});

test.each([
  [17, null],
  [18, 2],
  [24, 2],
])("with %i values in the last 24 hours the ratio is %j", async (samples, ratio) => {
  const body = (await answerFor([{ ...ROW, who_samples: String(samples) }])).json() as Latest;

  expect(body.features[0].properties.who_ratio).toBe(ratio);
  expect(body.features[0].properties.who_samples).toBe(samples);
});

test("a ratio is rounded to four decimals, which is more than any chart shows", async () => {
  const body = (await answerFor([{ ...ROW, who_mean_ugm3: "33.3333333333", who_guideline_ugm3: "25" }])).json() as Latest;

  expect(body.features[0].properties.who_ratio).toBe(1.3333);
});

test("a value that is not a number is null, never NaN", async () => {
  const row = { ...ROW, who_mean_ugm3: "NaN" };

  const body = (await answerFor([row])).json() as Latest;

  expect(body.features[0].properties.who_mean_ugm3).toBeNull();
  expect(body.features[0].properties.who_ratio).toBeNull();
});

test("without a guideline the comparison is all null", async () => {
  const row = { ...ROW, who_period: null, who_guideline_ugm3: null, who_mean_ugm3: null, who_samples: null };

  const body = (await answerFor([row])).json() as Latest;

  expect(body.features[0].properties).toMatchObject({
    who_period: null,
    who_guideline_ugm3: null,
    who_mean_ugm3: null,
    who_samples: null,
    who_ratio: null,
  });
});

test("an 8-hour mean has its ratio without a count of hourly values", async () => {
  const row = { ...ROW, who_period: "8h", who_guideline_ugm3: "100", who_mean_ugm3: "120", who_samples: null };

  const body = (await answerFor([row])).json() as Latest;

  expect(body.features[0].properties).toMatchObject({ who_period: "8h", who_ratio: 1.2, who_samples: null });
});

test("a pollutant that nobody measures is an empty list with the credit of the source", async () => {
  const response = await answerFor([]);

  expect(response.statusCode).toBe(200);
  const body = response.json() as Latest;
  expect(body.features).toEqual([]);
  expect(body.pollutant).toBe("NO2");
  expect(body.attribution).toContain("CC BY 4.0");
});

test.each([
  ["a missing pollutant", ""],
  ["a lower case code", "pollutant=no2"],
  ["a code with symbols", "pollutant=NO2';DROP"],
  ["a code that is too long", "pollutant=" + "A".repeat(21)],
])("%s is a 422 that names the parameter", async (_name, query) => {
  const response = await answerFor([], query);

  expect(response.statusCode).toBe(422);
  expect(response.headers["content-type"]).toContain("application/problem+json");
  expect(response.json().errors[0].loc).toEqual(["query", "pollutant"]);
  expect(response.body).not.toContain("DROP");
});

test("the code of the pollutant is passed to the database as a parameter, never written into the query", async () => {
  const asked: { text: string; params?: unknown[] }[] = [];
  const db = {
    async query(text: string, params?: unknown[]) {
      asked.push({ text, params });
      return { rows: [] } as never;
    },
  };
  const app = await buildApp({ db });

  await app.inject("/stations/latest?pollutant=NO2");

  expect(asked).toHaveLength(1);
  expect(asked[0].params).toEqual(["NO2"]);
  expect(asked[0].text).not.toContain("NO2");
});

test("a database that fails is a 500 with a fixed text", async () => {
  const app = await buildApp({ db: brokenDb() });

  const response = await app.inject("/stations/latest?pollutant=NO2");

  expect(response.statusCode).toBe(500);
  expect(response.body).not.toContain("reader_secret");
});

test("the description of the routes says that the pollutant is required and that a 422 is a problem document", async () => {
  const app = await buildApp({ db: fakeDb() });

  const document = (await app.inject("/openapi.json")).json();

  const operation = document.paths["/stations/latest"].get;
  expect(operation.parameters).toEqual([expect.objectContaining({ name: "pollutant", in: "query", required: true })]);
  expect(Object.keys(operation.responses["422"].content)).toEqual(["application/problem+json"]);
  const item = operation.responses["200"].content["application/json"].schema.properties.features.items.properties.properties;
  expect(item.properties.who_ratio.nullable).toBe(true);
});
