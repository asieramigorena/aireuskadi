// The colour of a unit by the tonnes that were declared in it per square kilometre, and the colour
// of a station by how its latest value compares with the WHO guideline.
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

// --- the air quality: the value of a station over the WHO guideline ---------------------------

/** Where the scale of the air quality ends: from twice the guideline everything is the same red, so
 * that one very bad station does not make the others look the same. */
export const RATIO_MAX = 2;

// Blue and green well under the guideline, yellow at it (that is the line that matters), red from
// twice it. The stops are the ratios where each colour is exact; in between it is a mix.
const RATIO_STOPS: { at: number; color: Color }[] = [
  { at: 0, color: [1, 152, 189, 235] },
  { at: 0.5, color: [73, 200, 160, 235] },
  { at: 1, color: [254, 224, 100, 235] },
  { at: RATIO_MAX, color: [209, 55, 78, 240] },
];

/** The colour of a ratio with the WHO guideline. No ratio (null) is the grey of no data. */
export function ratioColor(ratio: number | null): Color {
  if (ratio === null || !Number.isFinite(ratio)) return [...NO_DATA];
  const value = Math.min(Math.max(ratio, 0), RATIO_MAX);
  const upper = RATIO_STOPS.findIndex((stop) => stop.at >= value);
  if (upper === 0) return [...RATIO_STOPS[0].color];
  const from = RATIO_STOPS[upper - 1];
  const to = RATIO_STOPS[upper];
  const share = (value - from.at) / (to.at - from.at);
  return from.color.map((channel, i) => Math.round(channel + (to.color[i] - channel) * share)) as Color;
}

/** The scale as a CSS gradient, for the legend: from 0 to twice the guideline. */
export function ratioLegendGradient(): string {
  const stops = RATIO_STOPS.map(({ at, color: [r, g, b] }) => `rgb(${r} ${g} ${b}) ${(at / RATIO_MAX) * 100}%`);
  return `linear-gradient(to right, ${stops.join(", ")})`;
}
