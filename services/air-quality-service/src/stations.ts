// GET /stations: the stations of the air quality network as GeoJSON points.
import type { FastifyInstance } from "fastify";
import type { Db } from "./db.js";

// The licence of Open Data Euskadi (CC BY 4.0) asks to credit the source. The text goes with the
// data, as in the emissions service, so whoever uses the data receives it together with them.
export const ATTRIBUTION = "Open Data Euskadi, air quality network / Gobierno Vasco, CC BY 4.0";

const STATIONS = `
  SELECT s.id, s.code, s.name, s.area_type, s.municipality_code, m.name AS municipality_name,
         ST_AsGeoJSON(s.geom, 6)::json AS geometry
  FROM core.station s
  JOIN core.municipality m ON m.ine_code = s.municipality_code
  ORDER BY s.code`;

interface StationRow {
  id: number;
  code: string;
  name: string;
  area_type: string | null;
  municipality_code: string;
  municipality_name: string;
  geometry: { type: string; coordinates: number[] } | null;
}

// A station without a position is listed with null, not left out: it still has data.
export const pointGeometry = {
  type: "object",
  nullable: true,
  properties: {
    type: { type: "string", enum: ["Point"] },
    coordinates: { type: "array", items: { type: "number" } },
  },
} as const;

const feature = {
  type: "object",
  required: ["type", "geometry", "properties"],
  properties: {
    type: { type: "string", enum: ["Feature"] },
    geometry: pointGeometry,
    properties: {
      type: "object",
      required: ["id", "code", "name", "area_type", "municipality_code", "municipality_name"],
      properties: {
        id: { type: "integer" },
        code: { type: "string", description: "The id of the station in the air quality network." },
        name: { type: "string" },
        area_type: { type: "string", nullable: true, description: "urban, suburban, rural..." },
        municipality_code: { type: "string", description: "INE code." },
        municipality_name: { type: "string" },
      },
    },
  },
} as const;

const collection = {
  type: "object",
  required: ["type", "attribution", "features"],
  properties: {
    type: { type: "string", enum: ["FeatureCollection"] },
    attribution: { type: "string" },
    features: { type: "array", items: feature },
  },
} as const;

export async function stationRoutes(app: FastifyInstance, { db }: { db: Db }) {
  app.get(
    "/stations",
    {
      schema: {
        summary: "Stations of the air quality network",
        response: { 200: collection },
      },
    },
    async () => {
      const { rows } = await db.query<StationRow>(STATIONS);
      return {
        type: "FeatureCollection",
        attribution: ATTRIBUTION,
        features: rows.map((row) => ({
          type: "Feature",
          geometry: row.geometry,
          properties: {
            id: row.id,
            code: row.code,
            name: row.name,
            area_type: row.area_type,
            municipality_code: row.municipality_code,
            municipality_name: row.municipality_name,
          },
        })),
      };
    },
  );
}
