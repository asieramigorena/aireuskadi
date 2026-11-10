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
