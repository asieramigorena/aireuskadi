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

/** The latest hourly value of a pollutant at a station, and how it compares with the WHO guideline. */
export interface StationReading {
  pollutant: string;
  /** ISO 8601, UTC. */
  ts: string;
  value: number;
  /** As the network publishes it: µg/m3, mg/m3... */
  unit: string;
  /** The averaging period of the guideline it is compared with; null if the pollutant has none. */
  who_period: "24h" | "8h" | null;
  who_guideline_ugm3: number | null;
  who_mean_ugm3: number | null;
  /** Hourly values behind the 24-hour mean (24 if complete). */
  who_samples: number | null;
  /** null without a guideline or with fewer than 18 hourly values. */
  who_ratio: number | null;
}

export interface UnitStation {
  id: number;
  code: string;
  name: string;
  geometry: { type: string; coordinates: number[] } | null;
  readings: StationReading[];
}

/** Why there is nothing to show: no station, stations without values, or a district/territory. */
export type AirQualityReason = "no_station" | "no_data" | "level_not_supported";

export interface UnitAirQuality {
  /** The credit that the licence of the data asks for. */
  attribution: string;
  measured: boolean;
  reason: AirQualityReason | null;
  /** null for a district or a territory; empty for a municipality without stations. */
  stations: UnitStation[] | null;
}

export interface UnitCard {
  code: string;
  level: Level;
  name: string;
  area_km2: number;
  district: UnitReference | null;
  territory: UnitReference | null;
  emissions: UnitEmission[];
  /** null when the air quality service could not answer: the card is still the card. */
  air_quality: UnitAirQuality | null;
}
