// GET /units/{code}/stations: the stations of a municipality, each with its latest value of every
// pollutant it measures and how it compares with the WHO guideline (the same reading that
// /stations/latest gives). It is what the panel of a unit shows, and what the gateway adds to the
// card of the unit.
import type { FastifyInstance } from "fastify";
import type { Db } from "./db.js";
import { LATEST, type Row, reading, readingProperties } from "./latest.js";
import { INVALID_REQUEST, NOT_FOUND, problem } from "./problems.js";
import { ATTRIBUTION, pointGeometry } from "./stations.js";
import { UNITS, UNIT_CODE } from "./units.js";

const STATIONS = `
  SELECT s.id, s.code, s.name, ST_AsGeoJSON(s.geom, 6)::json AS geometry
  FROM core.station s
  WHERE s.municipality_code = $1
  ORDER BY s.code`;

// Every pollutant that exists: a station gives a reading for the ones it measures.
const POLLUTANTS = "SELECT array_agg(code ORDER BY code) AS codes FROM core.pollutant";

interface StationRow {
  id: number;
  code: string;
  name: string;
  geometry: { type: string; coordinates: number[] } | null;
}

const station = {
  type: "object",
  required: ["id", "code", "name", "geometry", "readings"],
  properties: {
    id: { type: "integer" },
    code: { type: "string" },
    name: { type: "string" },
    geometry: pointGeometry,
    readings: {
      type: "array",
      description: "The latest hourly value of each pollutant the station measures, ordered by pollutant. Empty if it has none.",
      items: {
        type: "object",
        required: ["pollutant", "ts", "value", "unit"],
        properties: {
          pollutant: { type: "string", description: "Code of the pollutant: NO2, PM10, O3..." },
          ...readingProperties,
        },
      },
    },
  },
} as const;

const answer = {
  type: "object",
  required: ["attribution", "unit", "measured", "reason", "stations"],
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
    measured: { type: "boolean", description: "False when there is nothing to show: see `reason`. Nothing is invented." },
    reason: { type: "string", nullable: true, description: "Why it is not measured: no_station (no station in the municipality), no_data (stations, but no hourly value of any pollutant) or level_not_supported (a district or a territory)." },
    stations: { type: "array", nullable: true, items: station, description: "Null for a district or a territory (see #33); empty for a municipality without stations." },
  },
} as const;

export async function unitStationRoutes(app: FastifyInstance, { db }: { db: Db }) {
  app.get<{ Params: { code: string } }>(
    "/units/:code/stations",
    {
      schema: {
        summary: "The stations of a municipality, with their latest value of each pollutant",
        params: {
          type: "object",
          required: ["code"],
          properties: {
            code: { type: "string", pattern: UNIT_CODE, description: "Code of the unit: 2 digits a territory, 4 a district, 5 a municipality." },
          },
        },
        response: { 200: answer, ...INVALID_REQUEST, ...NOT_FOUND },
      },
    },
    async (request, reply) => {
      const { code } = request.params;
      const kind = UNITS[code.length as keyof typeof UNITS];
      const found = (await db.query<{ name: string }>(kind.lookup, [code])).rows[0];
      if (!found) return problem(reply, 404, `Unit ${code} not found.`);

      const unit = { code, name: found.name, level: kind.level };
      const base = { attribution: ATTRIBUTION, unit };
      if (kind.level !== "municipality") return { ...base, measured: false, reason: "level_not_supported", stations: null };

      const stations = (await db.query<StationRow>(STATIONS, [code])).rows;
      if (stations.length === 0) return { ...base, measured: false, reason: "no_station", stations: [] };

      const codes = (await db.query<{ codes: string[] | null }>(POLLUTANTS)).rows[0]?.codes ?? [];
      const rows = (await db.query<Row>(LATEST, [codes, code])).rows;
      const byStation = new Map<number, Row[]>();
      for (const row of rows) byStation.set(row.id, [...(byStation.get(row.id) ?? []), row]);

      return {
        ...base,
        measured: rows.length > 0,
        reason: rows.length > 0 ? null : "no_data",
        stations: stations.map((row) => ({
          id: row.id,
          code: row.code,
          name: row.name,
          geometry: row.geometry,
          readings: (byStation.get(row.id) ?? []).map((r) => ({ pollutant: r.pollutant, ...reading(r) })),
        })),
      };
    },
  );
}
