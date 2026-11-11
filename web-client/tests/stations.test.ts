import { describe, expect, test } from "vitest";
import { meanRatioByMunicipality } from "../src/stations";
import type { StationFeature } from "../src/types";

const station = (municipality: string, ratio: number | null, geometry: StationFeature["geometry"] = null): StationFeature => ({
  type: "Feature",
  geometry,
  properties: {
    id: 1,
    code: "S",
    name: "S",
    municipality_code: municipality,
    ts: "2026-11-11T14:00:00.000Z",
    value: 1,
    unit: "µg/m3",
    who_period: "24h",
    who_guideline_ugm3: 25,
    who_mean_ugm3: null,
    who_samples: 24,
    who_ratio: ratio,
  },
});

describe("meanRatioByMunicipality: the colour that the ground of a municipality has in the map of the air quality", () => {
  test("is the mean of the ratios of its stations", () => {
    const means = meanRatioByMunicipality([station("48020", 0.4), station("48020", 1.2), station("48020", 0.8)]);

    expect(means.get("48020")).toBeCloseTo(0.8, 10);
  });

  test("each municipality has its own mean", () => {
    const means = meanRatioByMunicipality([station("48020", 0.4), station("20069", 2), station("48020", 0.6)]);

    expect(means.get("48020")).toBeCloseTo(0.5, 10);
    expect(means.get("20069")).toBe(2);
    expect(means.size).toBe(2);
  });

  test("a station without a ratio is not a zero: it is left out of the mean", () => {
    const means = meanRatioByMunicipality([station("48020", 1), station("48020", null), station("48020", 1)]);

    expect(means.get("48020")).toBe(1);
  });

  test("a municipality whose stations have no ratio has no mean, and so it is not painted: nothing is invented", () => {
    const means = meanRatioByMunicipality([station("48020", null), station("48020", null)]);

    expect(means.has("48020")).toBe(false);
    expect(means.size).toBe(0);
  });

  test("what is not a number is left out too", () => {
    const means = meanRatioByMunicipality([station("48020", Number.NaN), station("48020", Number.POSITIVE_INFINITY), station("48020", 0.5)]);

    expect(means.get("48020")).toBe(0.5);
  });

  test("a station without a position still counts: it has data, it is only not drawn", () => {
    const means = meanRatioByMunicipality([station("48020", 1, null), station("48020", 3, { type: "Point", coordinates: [-2.9, 43.2] })]);

    expect(means.get("48020")).toBe(2);
  });

  test("a municipality without stations is not in the answer, and no stations at all is an empty answer", () => {
    expect(meanRatioByMunicipality([station("48020", 1)]).has("01001")).toBe(false);
    expect(meanRatioByMunicipality([]).size).toBe(0);
  });
});
