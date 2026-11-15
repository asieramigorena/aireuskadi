// GET /units/{code}/exposure: how the air that a municipality breathes compares with the WHO annual
// guideline, from what its stations measured in a year.
import type { FastifyInstance } from "fastify";
import type { Db } from "./db.js";
import { INVALID_REQUEST, NOT_FOUND, invalidParameter, problem } from "./problems.js";
import { ATTRIBUTION } from "./stations.js";
import { KNOWN_UNIT, MIN_COVERAGE, TO_UGM3, UNITS, UNIT_CODE } from "./units.js";

// The mean is the one of unit_indicator (which the map uses): the average of every hourly value
// of the stations of the municipality, each in ug/m3 with its own unit. The coverage is how many
// hours of the year have a value from at least one station. The year is a UTC year.
const DATA = `
  SELECT AVG(m.value * ${TO_UGM3}) AS mean_ugm3,
         COUNT(DISTINCT m.ts) AS hours,
         COUNT(DISTINCT m.station_id) AS stations,
         (SELECT COUNT(*) FROM core.station WHERE municipality_code = $1) AS stations_total
  FROM core.measurement m
  JOIN core.station s ON s.id = m.station_id
  WHERE s.municipality_code = $1 AND m.pollutant_code = $2 AND m.averaging_period = '1h'
    AND m.ts >= $3::timestamptz AND m.ts < $4::timestamptz AND ${KNOWN_UNIT}`;

const ANNUAL_GUIDELINE = `
  SELECT value_ugm3 FROM core.who_guideline
  WHERE pollutant_code = $1 AND averaging_period = 'annual'
  ORDER BY edition DESC
  LIMIT 1`;

// Years that can be asked for: the data of the network is far more recent, but the range only has
// to keep the dates valid; a year without values is "not measured".
const MIN_YEAR = 1900;
const MAX_YEAR = 2100;

const round = (value: number, decimals: number) => {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
};

const nullable = (type: "string" | "number" | "integer" | "boolean", description?: string) =>
  ({ type, nullable: true, ...(description ? { description } : {}) }) as const;

const exposure = {
  type: "object",
  required: ["attribution", "unit", "pollutant", "year", "measured", "reason"],
  properties: {
    attribution: { type: "string" },
    unit: {
      type: "object",
      required: ["code", "name", "level"],
      properties: {
        code: { type: "string" },
        name: { type: "string" },
        level: { type: "string", enum: ["territory", "district", "municipality"] },
      },
    },
    pollutant: { type: "string" },
    year: { type: "integer" },
    measured: { type: "boolean", description: "False when there is nothing to show: see `reason`. Nothing is invented." },
    reason: nullable("string", "Why it is not measured: no_station (no station in the municipality), no_data (stations, but no hourly value of the pollutant in that year) or level_not_supported (a district or a territory)."),
    stations: nullable("integer", "Stations of the municipality with at least one value that year."),
    stations_total: nullable("integer", "Stations of the municipality."),
    mean_ugm3: nullable("number", "The mean of every hourly value of the year of those stations, in ug/m3. It is a mean of values, not of stations: a station with more values weighs more, as in the map."),
    guideline_ugm3: nullable("number", "The WHO annual guideline (most recent edition), in ug/m3. Null if the pollutant has none."),
    who_ratio: nullable("number", "mean_ugm3 / guideline_ugm3. It is a ratio, not a verdict: look at `coverage_ok` before trusting it."),
    hours: nullable("integer", "Hours of the year with a value from at least one station."),
    coverage: nullable("number", "hours over the hours of the year (8760, or 8784 in a leap year): the hours in which at least one station has a value, so two stations at the same hour are one hour."),
    coverage_ok: nullable("boolean", "True when the coverage is at least 75 %, which the WHO asks for an annual mean. It does not say that all the stations were measuring: compare `stations` with `stations_total`."),
  },
} as const;

interface Params {
  code: string;
}
interface Query {
  pollutant: string;
  year: string;
}

export async function exposureRoutes(app: FastifyInstance, { db }: { db: Db }) {
  app.get<{ Params: Params; Querystring: Query }>(
    "/units/:code/exposure",
    {
      schema: {
        summary: "Exposure of a municipality to a pollutant in a year, against the WHO annual guideline",
        params: {
          type: "object",
          required: ["code"],
          properties: {
            code: { type: "string", pattern: UNIT_CODE, description: "Code of the unit: 2 digits a territory, 4 a district, 5 a municipality." },
          },
        },
        querystring: {
          type: "object",
          required: ["pollutant", "year"],
          properties: {
            pollutant: { type: "string", pattern: "^[A-Z0-9_]+$", maxLength: 20, description: "Code of the pollutant: NO2, PM10, O3..." },
            // Text with a pattern, not an integer: the schema would turn "0x7e8" or "+2026" into a
            // number and one year would have many URLs. The range is checked below.
            year: { type: "string", pattern: "^[0-9]{4}$", description: "Year, four digits (UTC)." },
          },
        },
        response: { 200: exposure, ...INVALID_REQUEST, ...NOT_FOUND },
      },
    },
    async (request, reply) => {
      const { code } = request.params;
      const { pollutant } = request.query;
      const year = Number(request.query.year);
      if (year < MIN_YEAR || year > MAX_YEAR) {
        return invalidParameter(reply, ["query", "year"], `The year has to be between ${MIN_YEAR} and ${MAX_YEAR}.`, "range");
      }

      const kind = UNITS[code.length as keyof typeof UNITS];
      const found = (await db.query<{ name: string }>(kind.lookup, [code])).rows[0];
      if (!found) return problem(reply, 404, `Unit ${code} not found.`);

      const nothing = {
        stations: null,
        stations_total: null,
        mean_ugm3: null,
        guideline_ugm3: null,
        who_ratio: null,
        hours: null,
        coverage: null,
        coverage_ok: null,
      };
      const answer = { attribution: ATTRIBUTION, unit: { code, name: found.name, level: kind.level }, pollutant, year };

      if (kind.level !== "municipality") return { ...answer, ...nothing, measured: false, reason: "level_not_supported" };

      const from = new Date(Date.UTC(year, 0, 1));
      const to = new Date(Date.UTC(year + 1, 0, 1));
      const row = (await db.query<{ mean_ugm3: string | null; hours: string; stations: string; stations_total: string }>(DATA, [code, pollutant, from.toISOString(), to.toISOString()])).rows[0];
      const stationsTotal = Number(row.stations_total);
      const stations = Number(row.stations);
      const hours = Number(row.hours);
      if (stationsTotal === 0) return { ...answer, ...nothing, stations: 0, stations_total: 0, measured: false, reason: "no_station" };
      if (hours === 0 || row.mean_ugm3 === null) {
        return { ...answer, ...nothing, stations: 0, stations_total: stationsTotal, measured: false, reason: "no_data" };
      }

      const guideline = (await db.query<{ value_ugm3: string }>(ANNUAL_GUIDELINE, [pollutant])).rows[0];
      const mean = Number(row.mean_ugm3);
      const limit = guideline ? Number(guideline.value_ugm3) : null;
      const hoursInYear = (to.getTime() - from.getTime()) / 3_600_000;
      return {
        ...answer,
        measured: true,
        reason: null,
        stations,
        stations_total: stationsTotal,
        mean_ugm3: round(mean, 3),
        guideline_ugm3: limit,
        who_ratio: limit && limit > 0 ? round(mean / limit, 4) : null,
        hours,
        coverage: round(hours / hoursInYear, 4),
        coverage_ok: hours / hoursInYear >= MIN_COVERAGE,
      };
    },
  );
}
