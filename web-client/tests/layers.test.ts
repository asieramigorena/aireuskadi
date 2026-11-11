import { describe, expect, test, vi } from "vitest";
import { buildLayers } from "../src/layers";
import { colorFor } from "../src/scale";
import type { Point, UnitCollection } from "../src/types";

const POINTS: Point[] = [
  [-2.9, 43.2, 1500],
  [-2.8, 43.3, 500],
];

const UNITS: UnitCollection = {
  type: "FeatureCollection",
  attribution: "credit",
  features: [
    { type: "Feature", geometry: null, properties: { code: "01001", name: "A", declared_t: 100, t_km2: 10, who_ratio: null } },
    { type: "Feature", geometry: null, properties: { code: "01002", name: "B", declared_t: null, t_km2: null, who_ratio: null } },
    { type: "Feature", geometry: null, properties: { code: "01003", name: "C", declared_t: 0, t_km2: 0, who_ratio: null } },
    { type: "Feature", geometry: null, properties: { code: "01004", name: "D", declared_t: 30, t_km2: 3, who_ratio: null } },
  ],
};

// Layers of deck.gl keep what they were given in `props`; the accessors are plain functions.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;
const propsOf = (layer: unknown) => (layer as { props: Props }).props;

describe("buildLayers", () => {
  test("the units go below and the hexagons above, and without units only the hexagons", () => {
    const layers = buildLayers(POINTS, UNITS, vi.fn());

    expect(layers.map((layer) => layer.id)).toEqual(["units", "hexagons"]);
    expect(buildLayers(POINTS, null, vi.fn()).map((layer) => layer.id)).toEqual(["hexagons"]);
  });

  test("the hexagons cannot be clicked, so that a click always reaches the unit under them", () => {
    const [units, hexagons] = buildLayers(POINTS, UNITS, vi.fn()).map(propsOf);

    expect(units.pickable).toBe(true);
    expect(hexagons.pickable).toBe(false);
  });

  test("the hexagons are 3D columns of the sum of the kilograms of the facilities in each one", () => {
    const [, hexagons] = buildLayers(POINTS, UNITS, vi.fn()).map(propsOf);

    expect(hexagons.extruded).toBe(true);
    expect(hexagons.elevationAggregation).toBe("SUM");
    expect(hexagons.colorAggregation).toBe("SUM");
    expect(hexagons.getPosition(POINTS[0])).toEqual([-2.9, 43.2]);
    expect(hexagons.getElevationWeight(POINTS[0])).toBe(1500);
    expect(hexagons.getColorWeight(POINTS[1])).toBe(500);
  });

  test("the radius of the hexagons is the one that is given, and the columns are as tall as before for their width", () => {
    const [, big] = buildLayers(POINTS, UNITS, vi.fn(), 1500).map(propsOf);
    const [, small] = buildLayers(POINTS, UNITS, vi.fn(), 300).map(propsOf);

    expect(big.radius).toBe(1500);
    expect(big.elevationRange).toEqual([0, 6000]);
    // A smaller hexagon with a column as tall as a big one would be a needle.
    expect(small.radius).toBe(300);
    expect(small.elevationRange).toEqual([0, 1200]);
  });

  test("without a radius the hexagons are the biggest ones, as before", () => {
    const [, hexagons] = buildLayers(POINTS, UNITS, vi.fn()).map(propsOf);

    expect(hexagons.radius).toBe(1500);
  });

  test("a unit is painted by its density against the biggest one, and one without data is grey", () => {
    const [units] = buildLayers(POINTS, UNITS, vi.fn()).map(propsOf);
    const [a, b, c, d] = UNITS.features;

    expect(units.getFillColor(a)).toEqual(colorFor(10, 10));
    expect(units.getFillColor(b)).toEqual(colorFor(null, 10));
    expect(units.getFillColor(c)).toEqual(colorFor(0, 10));
    // In the middle of the scale, where the biggest density decides the colour.
    expect(units.getFillColor(d)).toEqual(colorFor(3, 10));
    expect(units.getFillColor(d)).not.toEqual(colorFor(3, 1));
  });

  test("clicking a unit tells its code, and clicking nothing tells nothing", () => {
    const onUnit = vi.fn();
    const [units] = buildLayers(POINTS, UNITS, onUnit).map(propsOf);

    units.onClick({ object: UNITS.features[1] });
    units.onClick({ object: null });

    expect(onUnit).toHaveBeenCalledTimes(1);
    expect(onUnit).toHaveBeenCalledWith("01002");
  });

  test("the colours are painted again when the biggest density changes", () => {
    const [units] = buildLayers(POINTS, UNITS, vi.fn()).map(propsOf);

    expect(units.updateTriggers.getFillColor).toEqual([10]);
  });
});
