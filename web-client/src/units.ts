// The units that the map draws. The boundaries and the numbers come apart from the gateway: the
// boundaries weigh (about 0.7 MB for the municipalities) and are the same for every pollutant and
// year, so they come once; the numbers are small and come at every change. Here they meet, by code.
import type { BoundaryCollection, UnitCollection, UnitIndicators } from "./types";

/** The boundaries with the numbers of each unit put in. `indicators` null (the map of the air quality,
 * which colours the units with its stations) and a unit with no numbers have no data, never zero. */
export function withIndicators(boundaries: BoundaryCollection, indicators: UnitIndicators[] | null): UnitCollection {
  const byCode = new Map((indicators ?? []).map((unit) => [unit.code, unit]));
  return {
    type: "FeatureCollection",
    attribution: boundaries.attribution,
    features: boundaries.features.map(({ geometry, properties: { code, name } }) => {
      const found = byCode.get(code);
      return {
        type: "Feature",
        geometry,
        properties: {
          code,
          name,
          declared_t: found?.declared_t ?? null,
          t_km2: found?.t_km2 ?? null,
          who_ratio: found?.who_ratio ?? null,
        },
      };
    }),
  };
}

