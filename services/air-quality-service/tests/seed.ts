// The rows that the tests with a database need. Their codes start with T so that they are not
// mistaken for real ones, and everything is rolled back with the transaction of the test.
import type { Db } from "../src/db.js";

export async function addMunicipality(db: Db, code = "98001", name = "Testville") {
  await db.query(
    "INSERT INTO core.territory (code, name) VALUES ('98', 'Test') ON CONFLICT DO NOTHING",
  );
  await db.query(
    "INSERT INTO core.district (code, territory_code, name) VALUES ('9801', '98', 'Test') ON CONFLICT DO NOTHING",
  );
  await db.query(
    "INSERT INTO core.municipality (ine_code, district_code, name, area_km2) VALUES ($1, '9801', $2, 10) ON CONFLICT DO NOTHING",
    [code, name],
  );
}

export interface NewStation {
  code: string;
  name?: string;
  areaType?: string | null;
  municipality?: string;
  /** [longitude, latitude]; no geometry if it is null. */
  at?: [number, number] | null;
}

/** Adds a station (and the municipality it is in) and gives back its id. */
export async function addStation(db: Db, station: NewStation): Promise<number> {
  const municipality = station.municipality ?? "98001";
  await addMunicipality(db, municipality);
  const at = station.at === undefined ? [-2.935, 43.263] : station.at;
  const { rows } = await db.query<{ id: number }>(
    `INSERT INTO core.station (municipality_code, code, name, area_type, geom)
     VALUES ($1, $2, $3, $4, CASE WHEN $5::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint($5::float8, $6::float8), 4326) END)
     RETURNING id`,
    [
      municipality,
      station.code,
      station.name ?? `Station ${station.code}`,
      station.areaType === undefined ? "urban" : station.areaType,
      at?.[0] ?? null,
      at?.[1] ?? null,
    ],
  );
  return rows[0].id;
}

export async function addPollutant(db: Db, code: string) {
  await db.query("INSERT INTO core.pollutant (code, name) VALUES ($1, $1) ON CONFLICT DO NOTHING", [code]);
}

/** A WHO guideline, always in ug/m3, as the table stores it. */
export async function addGuideline(db: Db, pollutant: string, period: string, valueUgm3: number, edition = 2021) {
  await addPollutant(db, pollutant);
  await db.query(
    "INSERT INTO core.who_guideline (pollutant_code, averaging_period, edition, value_ugm3) VALUES ($1, $2, $3, $4)",
    [pollutant, period, edition, valueUgm3],
  );
}

export interface Reading {
  /** ISO time in UTC. */
  ts: string;
  value: number;
  unit?: string;
  /** "1h" (the hourly value, the default) or "8h" (the running mean of 8 hours). */
  period?: string;
}

export async function addReadings(db: Db, stationId: number, pollutant: string, readings: Reading[]) {
  await addPollutant(db, pollutant);
  for (const r of readings) {
    await db.query(
      "INSERT INTO core.measurement (station_id, pollutant_code, ts, averaging_period, value, unit) VALUES ($1, $2, $3, $4, $5, $6)",
      [stationId, pollutant, r.ts, r.period ?? "1h", r.value, r.unit ?? "µg/m3"],
    );
  }
}

/** `count` hourly values that end at `endIso` (included), all equal to `value`. */
export function hourly(endIso: string, count: number, value: number, unit = "µg/m3"): Reading[] {
  const end = Date.parse(endIso);
  return Array.from({ length: count }, (_, i) => ({
    ts: new Date(end - (count - 1 - i) * 3_600_000).toISOString(),
    value,
    unit,
  }));
}

/**
 * `count` hourly values in one statement (a year has 8760 hours: one insert for each would be slow),
 * starting at `startIso`, all equal to `value`.
 */
export async function addHourlyRun(
  db: Db,
  stationId: number,
  pollutant: string,
  startIso: string,
  count: number,
  value: number,
  unit = "µg/m3",
) {
  await addPollutant(db, pollutant);
  await db.query(
    `INSERT INTO core.measurement (station_id, pollutant_code, ts, averaging_period, value, unit)
     SELECT $1, $2, $3::timestamptz + (n * interval '1 hour'), '1h', $4, $5
     FROM generate_series(0, $6::int - 1) AS n`,
    [stationId, pollutant, startIso, value, unit, count],
  );
}
