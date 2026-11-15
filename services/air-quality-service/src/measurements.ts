// GET /stations/{id}/measurements: the time series of one pollutant at one station.
import type { FastifyInstance } from "fastify";
import type { Db } from "./db.js";
import { INVALID_REQUEST, NOT_FOUND, invalidParameter, problem } from "./problems.js";
import { ATTRIBUTION } from "./stations.js";
import { KNOWN_UNIT, MIN_HOURS_FOR_A_MEAN, TO_UGM3 } from "./units.js";

// A series cannot be as long as the caller wants: an hourly one is at most 31 days (744 points)
// and a daily one at most 366 days (one year), which is what a chart can draw and keeps each
// request cheap. Longer is a 422 that says the limit, not an answer that is silently cut.
const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const MAX_RANGE = { hour: 31 * DAY, day: 366 * DAY } as const;
const MAX_TEXT = { hour: "The range of an hourly series is at most 31 days.", day: "The range of a daily series is at most 366 days." };

// The id of a station is the integer of the database: the largest number that it holds. A number
// above it is a station that does not exist (PostgreSQL would refuse it, and that was a 500).
const MAX_ID = 2_147_483_647;

const STATION = "SELECT id, code, name FROM core.station WHERE id = $1";

// The range is [from, to): `from` is in and `to` is out. The key of the table is (station,
// pollutant, time), so both queries read a range of it.
const HOURLY = `
  SELECT m.ts, m.value * ${TO_UGM3} AS ugm3
  FROM core.measurement m
  WHERE m.station_id = $1 AND m.pollutant_code = $2 AND m.averaging_period = '1h'
    AND m.ts >= $3 AND m.ts < $4 AND ${KNOWN_UNIT}
  ORDER BY m.ts`;

// A day is a calendar day in UTC, whatever the time zone of the session.
const DAILY = `
  SELECT date_trunc('day', m.ts AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS day,
         AVG(m.value * ${TO_UGM3}) AS ugm3, COUNT(*) AS hours
  FROM core.measurement m
  WHERE m.station_id = $1 AND m.pollutant_code = $2 AND m.averaging_period = '1h'
    AND m.ts >= $3 AND m.ts < $4 AND ${KNOWN_UNIT}
  GROUP BY 1
  ORDER BY 1`;

const round = (value: string) => Math.round(Number(value) * 1000) / 1000;

const series = {
  type: "object",
  required: ["attribution", "station", "pollutant", "interval", "unit", "from", "to", "points"],
  properties: {
    attribution: { type: "string" },
    station: {
      type: "object",
      required: ["id", "code", "name"],
      properties: { id: { type: "integer" }, code: { type: "string" }, name: { type: "string" } },
    },
    pollutant: { type: "string" },
    interval: { type: "string", enum: ["hour", "day"] },
    unit: { type: "string", description: "Always ug/m3: every value is converted from the unit it was published in." },
    from: { type: "string", description: "Start of the range, included. ISO 8601 in UTC." },
    to: { type: "string", description: "End of the range, not included. ISO 8601 in UTC." },
    points: {
      type: "array",
      items: {
        type: "object",
        required: ["ts", "value"],
        properties: {
          ts: { type: "string", description: "The hour, or the start of the day (00:00 UTC)." },
          value: { type: "number", description: "The hourly value, or the mean of the hours that the day has." },
          hours: { type: "integer", description: "Daily series only: the hours that the mean is made of (1 to 24)." },
          coverage_ok: { type: "boolean", description: "Daily series only: true when the day has at least 18 hours." },
        },
      },
    },
  },
} as const;

interface Query {
  pollutant: string;
  from: string;
  to: string;
  interval: "hour" | "day";
}

export async function measurementRoutes(app: FastifyInstance, { db }: { db: Db }) {
  app.get<{ Params: { id: string }; Querystring: Query }>(
    "/stations/:id/measurements",
    {
      schema: {
        summary: "Time series of one pollutant at one station, by hour or by day",
        params: {
          type: "object",
          required: ["id"],
          properties: {
            id: {
              type: "string",
              // Only plain decimal digits, no zero in front: one URL for each station.
              pattern: "^[1-9][0-9]{0,9}$",
              description: "Id of the station: a positive integer written in plain digits.",
            },
          },
        },
        querystring: {
          type: "object",
          required: ["pollutant", "from", "to"],
          properties: {
            pollutant: { type: "string", pattern: "^[A-Z0-9_]+$", maxLength: 20, description: "Code of the pollutant: NO2, PM10, O3..." },
            from: { type: "string", format: "date-time", description: "Start of the range, included. ISO 8601 with a time zone; a `+` in an offset has to be written as %2B in the URL. With `interval=day` the first day is a whole UTC day that can be partial: it has only the hours from `from`, and `coverage_ok` says so." },
            to: { type: "string", format: "date-time", description: "End of the range, not included. At most 31 days after `from` for `hour`, 366 for `day`. With `interval=day` the last day can be partial too." },
            interval: { type: "string", enum: ["hour", "day"], default: "hour" },
          },
        },
        response: { 200: series, ...INVALID_REQUEST, ...NOT_FOUND },
      },
    },
    async (request, reply) => {
      const id = Number(request.params.id);
      const { pollutant, interval } = request.query;
      const from = new Date(request.query.from);
      const to = new Date(request.query.to);
      // The rules that the schema cannot say, before the database is asked anything. A leap second
      // ("23:59:60") is a valid date-time for the schema, and JavaScript cannot read it.
      if (Number.isNaN(from.getTime())) return invalidParameter(reply, ["query", "from"], "`from` is not a date that can be read.", "date");
      if (Number.isNaN(to.getTime())) return invalidParameter(reply, ["query", "to"], "`to` is not a date that can be read.", "date");
      if (to <= from) return invalidParameter(reply, ["query", "to"], "`to` must be after `from`.", "range_order");
      if (to.getTime() - from.getTime() > MAX_RANGE[interval]) {
        return invalidParameter(reply, ["query", "to"], MAX_TEXT[interval], "range_too_large");
      }

      if (id > MAX_ID) return problem(reply, 404, `Station ${id} not found.`);
      const station = (await db.query<{ id: number; code: string; name: string }>(STATION, [id])).rows[0];
      if (!station) return problem(reply, 404, `Station ${id} not found.`);

      const params = [id, pollutant, from, to];
      const points =
        interval === "hour"
          ? (await db.query<{ ts: Date; ugm3: string }>(HOURLY, params)).rows.map((row) => ({
              ts: row.ts.toISOString(),
              value: round(row.ugm3),
            }))
          : (await db.query<{ day: Date; ugm3: string; hours: string }>(DAILY, params)).rows.map((row) => ({
              ts: row.day.toISOString(),
              value: round(row.ugm3),
              hours: Number(row.hours),
              coverage_ok: Number(row.hours) >= MIN_HOURS_FOR_A_MEAN,
            }));

      return {
        attribution: ATTRIBUTION,
        station: { id: station.id, code: station.code, name: station.name },
        pollutant,
        interval,
        unit: "µg/m3",
        from: from.toISOString(),
        to: to.toISOString(),
        points,
      };
    },
  );
}
