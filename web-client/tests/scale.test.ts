import { describe, expect, test } from "vitest";
import { NO_DATA, RATIO_MAX, colorFor, legendGradient, maxDensity, ratioColor, ratioLegendGradient } from "../src/scale";
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

});

describe("maxDensity", () => {
  test("is the biggest density, and ignores the units without data", () => {
    expect(maxDensity([feature(3), feature(null), feature(12.5), feature(0)])).toBe(12.5);
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

describe("ratioColor: the air quality against the WHO guideline", () => {
  test("below half the guideline it is blue, at the guideline yellow, and from twice the guideline red", () => {
    expect(ratioColor(0)).toEqual([1, 152, 189, 235]);
    expect(ratioColor(0.5)).toEqual([73, 200, 160, 235]);
    expect(ratioColor(1)).toEqual([254, 224, 100, 235]);
    expect(ratioColor(RATIO_MAX)).toEqual([209, 55, 78, 240]);
  });

  test("the scale ends at twice the guideline: more is the same red, so that one station does not hide the rest", () => {
    expect(RATIO_MAX).toBe(2);
    expect(ratioColor(2.0001)).toEqual(ratioColor(2));
    expect(ratioColor(40)).toEqual(ratioColor(2));
  });

  test("no ratio is the grey of no data (and not a colour of the scale), also for what is not a number", () => {
    expect(ratioColor(null)).toEqual(NO_DATA);
    expect(ratioColor(Number.NaN)).toEqual(NO_DATA);
    expect(ratioColor(Number.POSITIVE_INFINITY)).toEqual(NO_DATA);
  });

});

describe("ratioLegendGradient", () => {
  test("has the stops of the scale, placed where the ratios are on the bar from 0 to twice the guideline", () => {
    expect(ratioLegendGradient()).toBe(
      "linear-gradient(to right, rgb(1 152 189) 0%, rgb(73 200 160) 25%, rgb(254 224 100) 50%, rgb(209 55 78) 100%)",
    );
  });
});
