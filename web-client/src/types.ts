// The shapes of what the gateway answers (the contract is the OpenAPI document of the services).

export type Level = "municipality" | "district" | "territory";

/** [lon, lat, kg] of a facility that declared the pollutant in the year. */
export type Point = [number, number, number];

export interface UnitProperties {
  code: string;
  name: string;
  /** null: nobody declared it, which is not the same as a declared zero. */
  declared_t: number | null;
  t_km2: number | null;
  /** null above the municipality, or when there is no station. */
  who_ratio: number | null;
}

export interface UnitFeature {
  type: "Feature";
  geometry: { type: string; coordinates: unknown } | null;
  properties: UnitProperties;
}

export interface UnitCollection {
  type: "FeatureCollection";
  /** The credit that the licence of the boundaries asks for. */
  attribution: string;
  features: UnitFeature[];
}

export interface UnitReference {
  code: string;
  name: string;
}

export interface UnitEmission {
  year: number;
  pollutant: string;
  name: string;
  declared_t: number | null;
  t_km2: number | null;
  who_ratio: number | null;
}

export interface UnitCard {
  code: string;
  level: Level;
  name: string;
  area_km2: number;
  district: UnitReference | null;
  territory: UnitReference | null;
  emissions: UnitEmission[];
}
