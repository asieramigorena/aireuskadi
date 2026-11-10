// GET /stations/latest: the latest hourly value of each station for a pollutant, and how it
// compares with the WHO guideline that has the same averaging period.
import type { FastifyInstance } from "fastify";
import type { Db } from "./db.js";
import { INVALID_REQUEST } from "./problems.js";
import { ATTRIBUTION, pointGeometry } from "./stations.js";
import { KNOWN_UNIT, MIN_HOURS_FOR_A_MEAN, TO_UGM3 } from "./units.js";

// The WHO 2021 guidelines have no value for one hour. An hourly value is not compared with a
// guideline of another period (a bad hour is not an exceeded day), so each pollutant is compared
// with the guideline it has, using the mean of the same length:
//   - 24 hours (PM2.5, PM10, NO2, SO2, CO): the mean of the hourly values of the TRAILING 24 hours
//     up to the latest one, if there are at least 18 (75 %, the coverage that the WHO asks for);
//   - 8 hours (O3): the latest running mean of 8 hours that the network publishes.
// It is an indicator, not a verdict: the WHO defines the 24-hour guideline on a calendar day (and
// allows a few days a year over it) and the 8-hour one on the highest 8-hour mean of the day, so a
// ratio over 1 here does not say that the guideline was exceeded. The 24-hour guideline is the one
// used when a pollutant has both; the most recent edition wins.

const LATEST = `
  WITH guideline AS (
    SELECT averaging_period AS period, value_ugm3
    FROM core.who_guideline
    WHERE pollutant_code = $1 AND averaging_period IN ('24h', '8h')
    ORDER BY edition DESC, (averaging_period <> '24h')
    LIMIT 1
  )
  SELECT s.id, s.code, s.name, s.municipality_code, ST_AsGeoJSON(s.geom, 6)::json AS geometry,
         l.ts, l.value, l.unit,
         g.period AS who_period, g.value_ugm3 AS who_guideline_ugm3,
         CASE g.period WHEN '24h' THEN d.mean_ugm3 WHEN '8h' THEN e.value_ugm3 END AS who_mean_ugm3,
         CASE g.period WHEN '24h' THEN d.samples END AS who_samples
  FROM core.station s
  -- One probe of the primary key (station, pollutant, time) per station, backwards: the cost does
  -- not grow with the history of the measurements, as it would if the table were scanned for the
  -- pollutant and then sorted.
  JOIN LATERAL (
    SELECT m.ts, m.value, m.unit
    FROM core.measurement m
    WHERE m.station_id = s.id AND m.pollutant_code = $1 AND m.averaging_period = '1h'
    ORDER BY m.ts DESC
    LIMIT 1
  ) l ON true
  LEFT JOIN guideline g ON true
  LEFT JOIN LATERAL (
    SELECT AVG(x.ugm3) AS mean_ugm3, COUNT(x.ugm3) AS samples
    FROM (
      SELECT m.value * ${TO_UGM3} AS ugm3
      FROM core.measurement m
      WHERE m.station_id = s.id AND m.pollutant_code = $1 AND m.averaging_period = '1h'
        AND m.ts > l.ts - interval '24 hours' AND m.ts <= l.ts AND ${KNOWN_UNIT}
    ) x
  ) d ON g.period = '24h'
  LEFT JOIN LATERAL (
    SELECT m.value * ${TO_UGM3} AS value_ugm3
    FROM core.measurement m
    WHERE m.station_id = s.id AND m.pollutant_code = $1 AND m.averaging_period = '8h'
      AND ${KNOWN_UNIT}
    ORDER BY m.ts DESC
    LIMIT 1
  ) e ON g.period = '8h'
  ORDER BY s.code`;

interface Row {
  id: number;
  code: string;
  name: string;
  municipality_code: string;
  geometry: { type: string; coordinates: number[] } | null;
  ts: Date;
  value: string;
  unit: string;
  who_period: string | null;
  who_guideline_ugm3: string | null;
  who_mean_ugm3: string | null;
  who_samples: string | null;
}

// A numeric of PostgreSQL can be NaN: it is written as null, which JSON can say, not as NaN.
const number = (value: string | null): number | null => {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/** The mean over the guideline, or null when there is nothing to compare or too little to trust. */
function ratio(row: Row): number | null {
  const mean = number(row.who_mean_ugm3);
  const guideline = number(row.who_guideline_ugm3);
  if (mean === null || guideline === null || guideline <= 0) return null;
  if (row.who_period === "24h" && (number(row.who_samples) ?? 0) < MIN_HOURS_FOR_A_MEAN) return null;
  return Math.round((mean / guideline) * 10_000) / 10_000;
}

const nullable = (type: "string" | "number" | "integer", description?: string) =>
  ({ type, nullable: true, ...(description ? { description } : {}) }) as const;

const feature = {
  type: "object",
  required: ["type", "geometry", "properties"],
  properties: {
    type: { type: "string", enum: ["Feature"] },
    geometry: pointGeometry,
    properties: {
      type: "object",
      required: ["id", "code", "name", "municipality_code", "ts", "value", "unit"],
      properties: {
        id: { type: "integer" },
        code: { type: "string" },
        name: { type: "string" },
        municipality_code: { type: "string" },
        ts: { type: "string", description: "Time of the latest hourly value, ISO 8601 in UTC." },
        value: { type: "number", description: "The latest hourly value, in `unit`. It can be old: see `ts`." },
        unit: { type: "string", description: "As the network publishes it: µg/m3, mg/m3..." },
        who_period: nullable("string", "Averaging period of the WHO guideline the value is compared with: 24h or 8h. Null if the pollutant has neither."),
        who_guideline_ugm3: nullable("number", "The WHO 2021 guideline (most recent edition), in ug/m3."),
        who_mean_ugm3: nullable("number", "For 24h: the mean of the trailing 24 hours up to `ts`. For 8h: the latest running mean of 8 hours. In ug/m3."),
        who_samples: nullable("integer", "Hourly values behind the 24-hour mean (24 if complete)."),
        who_ratio: nullable("number", "who_mean_ugm3 / who_guideline_ugm3, an indicator and not a verdict: the WHO defines the 24h guideline on a calendar day and the 8h one on the highest 8-hour mean of the day, so a value over 1 does not say that it was exceeded. Null without a guideline or with fewer than 18 hourly values."),
      },
    },
  },
} as const;

const collection = {
  type: "object",
  required: ["type", "attribution", "pollutant", "features"],
  properties: {
    type: { type: "string", enum: ["FeatureCollection"] },
    attribution: { type: "string" },
    pollutant: { type: "string" },
    features: { type: "array", items: feature },
  },
} as const;

export async function latestRoutes(app: FastifyInstance, { db }: { db: Db }) {
  app.get<{ Querystring: { pollutant: string } }>(
    "/stations/latest",
    {
      schema: {
        summary: "Latest hourly value of each station and its comparison with the WHO guideline",
        querystring: {
          type: "object",
          required: ["pollutant"],
          properties: {
            pollutant: { type: "string", pattern: "^[A-Z0-9_]+$", maxLength: 20, description: "Code of the pollutant: NO2, PM10, O3..." },
          },
        },
        response: { 200: collection, ...INVALID_REQUEST },
      },
    },
    async (request) => {
      const { pollutant } = request.query;
      const { rows } = await db.query<Row>(LATEST, [pollutant]);
      return {
        type: "FeatureCollection",
        attribution: ATTRIBUTION,
        pollutant,
        features: rows.map((row) => ({
          type: "Feature",
          geometry: row.geometry,
          properties: {
            id: row.id,
            code: row.code,
            name: row.name,
            municipality_code: row.municipality_code,
            ts: row.ts.toISOString(),
            value: Number(row.value),
            unit: row.unit,
            who_period: row.who_period,
            who_guideline_ugm3: number(row.who_guideline_ugm3),
            who_mean_ugm3: number(row.who_mean_ugm3),
            who_samples: number(row.who_samples),
            who_ratio: ratio(row),
          },
        })),
      };
    },
  );
}
