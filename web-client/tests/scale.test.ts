import { describe, expect, test } from "vitest";
import { NO_DATA, colorFor, legendGradient, maxDensity } from "../src/scale";
import type { UnitFeature } from "../src/types";

const feature = (t_km2: number | null): UnitFeature => ({
  type: "Feature",
  geometry: null,
  properties: { code: "1", name: "x", declared_t: t_km2, t_km2, who_ratio: null },
});

describe("colorFor", () => {
  test("no data is grey, whatever the maximum", () => {
    expect(colorFor(null, 100)).toEqual(NO_DATA);
    expect(colorFor(Number.NaN, 100)).toEqual(NO_DATA);
    expect(colorFor(null, 0)).toEqual(NO_DATA);
  });

  test("a declared zero has a colour of its own, not the grey of no data", () => {
    expect(colorFor(0, 100)).not.toEqual(NO_DATA);
  });

  test("the colours go from the lowest to the highest and each value has its own", () => {
    const steps = [0, 1, 10, 50, 100].map((value) => colorFor(value, 100).join(","));

    expect(new Set(steps).size).toBe(steps.length);
  });

  test("it is a logarithmic scale: one municipality with a huge density does not paint the rest the same", () => {
    // With a linear scale 1, 10 and 100 against 100000 would be almost the same colour.
    const [a, b, c] = [1, 10, 100].map((value) => colorFor(value, 100_000).join(","));

    expect(new Set([a, b, c]).size).toBe(3);
  });

  test("above the maximum it has the colour of the maximum, and below zero that of zero", () => {
    expect(colorFor(500, 100)).toEqual(colorFor(100, 100));
    expect(colorFor(-3, 100)).toEqual(colorFor(0, 100));
  });

  test("when everything is zero nothing divides by zero", () => {
    expect(colorFor(0, 0)).toEqual(colorFor(0, 100));
    for (const channel of colorFor(0, 0)) expect(Number.isFinite(channel)).toBe(true);
  });

  test("the channels are whole numbers between 0 and 255", () => {
    for (const value of [0, 0.001, 3, 77, 100, 1e9]) {
      for (const channel of colorFor(value, 100)) {
        expect(Number.isInteger(channel)).toBe(true);
        expect(channel).toBeGreaterThanOrEqual(0);
        expect(channel).toBeLessThanOrEqual(255);
      }
    }
  });
});

describe("maxDensity", () => {
  test("is the biggest density, and ignores the units without data", () => {
    expect(maxDensity([feature(3), feature(null), feature(12.5), feature(0)])).toBe(12.5);
  });

  test("is 0 when there is nothing", () => {
    expect(maxDensity([])).toBe(0);
    expect(maxDensity([feature(null)])).toBe(0);
  });
});

describe("legendGradient", () => {
  test("is the scale of the map from the lowest density to the highest, as a CSS gradient", () => {
    const css = legendGradient();

    expect(css.startsWith("linear-gradient(to right,")).toBe(true);
    const [low, high] = [colorFor(0, 100), colorFor(100, 100)];
    expect(css).toContain(`rgb(${low[0]} ${low[1]} ${low[2]})`);
    expect(css.endsWith(`rgb(${high[0]} ${high[1]} ${high[2]}))`)).toBe(true);
  });
});
