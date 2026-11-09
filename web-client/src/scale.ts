// The colour of a unit by the tonnes that were declared in it per square kilometre.
import type { UnitFeature } from "./types";

export type Color = [number, number, number, number];

/** Nobody declared it. Grey: it is not the colour of any value, and zero is not "no data". */
export const NO_DATA: Color = [130, 130, 130, 90];

// From pale yellow to deep red: more declared emissions, darker.
const STOPS: Color[] = [
  [253, 231, 150, 200],
  [244, 130, 70, 215],
  [160, 25, 60, 230],
];

/** The colour of `value`, on a logarithmic scale from 0 to `max`: a few units with a huge density
 * would otherwise make all the others look the same. */
export function colorFor(value: number | null, max: number): Color {
  if (value === null || !Number.isFinite(value)) return [...NO_DATA];
  // The logarithm of a negative number is not a number: below zero is zero.
  const position = max > 0 ? Math.min(Math.log1p(Math.max(value, 0)) / Math.log1p(max), 1) : 0;
  const scaled = position * (STOPS.length - 1);
  const from = Math.min(Math.floor(scaled), STOPS.length - 2);
  const share = scaled - from;
  return STOPS[from].map((channel, i) =>
    Math.round(channel + (STOPS[from + 1][i] - channel) * share),
  ) as Color;
}

/** The biggest density of the units, or 0 if none has data. */
export function maxDensity(features: UnitFeature[]): number {
  let max = 0;
  for (const { properties } of features) {
    if (properties.t_km2 !== null && properties.t_km2 > max) max = properties.t_km2;
  }
  return max;
}

/** The scale as a CSS gradient, for the legend. */
export function legendGradient(): string {
  const stops = STOPS.map(([r, g, b]) => `rgb(${r} ${g} ${b})`);
  return `linear-gradient(to right, ${stops.join(", ")})`;
}
