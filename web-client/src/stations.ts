// What the map of the air quality says about the ground, from the latest value of each station.
import type { StationFeature } from "./types";

/** The mean of the ratios with the WHO guideline of the stations of each municipality: the colour of
 * its ground in the map. A station without a ratio (too few values, or no guideline) is left out of
 * the mean and not counted as a zero, and a municipality whose stations have none is not in the
 * answer: there is no value to paint, and nothing is invented. */
export function meanRatioByMunicipality(stations: StationFeature[]): Map<string, number> {
  const sums = new Map<string, { sum: number; count: number }>();
  for (const { properties } of stations) {
    const ratio = properties.who_ratio;
    if (ratio === null || !Number.isFinite(ratio)) continue;
    const known = sums.get(properties.municipality_code) ?? { sum: 0, count: 0 };
    sums.set(properties.municipality_code, { sum: known.sum + ratio, count: known.count + 1 });
  }
  return new Map([...sums].map(([code, { sum, count }]) => [code, sum / count]));
}
