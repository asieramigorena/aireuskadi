import { describe, expect, test, vi } from "vitest";
import { FLAT_ALPHA, NEUTRAL_UNIT, buildAirLayers, buildLayers, columnHeight } from "../src/layers";
import { colorFor, ratioColor } from "../src/scale";
import type { Point, StationCollection, StationFeature, UnitCollection } from "../src/types";

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

const station = (code: string, municipality: string, ratio: number | null, at: [number, number] | null = [-2.9, 43.2]): StationFeature => ({
  type: "Feature",
  geometry: at && { type: "Point", coordinates: at },
  properties: {
    id: Number(code.replace(/\D/g, "")) || 1,
    code,
    name: `Station ${code}`,
    municipality_code: municipality,
    ts: "2026-11-11T14:00:00.000Z",
    value: 20,
    unit: "µg/m3",
    who_period: ratio === null ? null : "24h",
    who_guideline_ugm3: ratio === null ? null : 25,
    who_mean_ugm3: ratio === null ? null : ratio * 25,
    who_samples: ratio === null ? null : 24,
    who_ratio: ratio,
  },
});

const STATIONS: StationCollection = {
  type: "FeatureCollection",
  attribution: "credit",
  pollutant: "NO2",
  features: [station("A1", "48020", 0.4), station("A2", "48020", 1.2, [-2.8, 43.3]), station("A3", "01059", null, null), station("A4", "20069", null, [-1.9, 43.3])],
};

describe("columnHeight: how tall the column of a station is", () => {
  test("a station without a ratio and one at zero are low columns that can still be seen, never needles or nothing", () => {
    expect(columnHeight(null, 1000)).toBe(500);
    expect(columnHeight(0, 1000)).toBe(500);
  });

  test("from twice the guideline the column is the tallest, as the colour is the same red", () => {
    expect(columnHeight(2, 1000)).toBe(8000);
    expect(columnHeight(5, 1000)).toBe(8000);
    expect(columnHeight(1, 1000)).toBe(4250);
  });

  test("a higher ratio is a taller column, and a smaller radius a lower one", () => {
    const heights = [0, 0.5, 1, 1.5, 2].map((ratio) => columnHeight(ratio, 1000));

    expect(heights).toEqual([...heights].sort((a, b) => a - b));
    expect(new Set(heights).size).toBe(heights.length);
    expect(columnHeight(1, 300)).toBeLessThan(columnHeight(1, 1000));
  });

  test("a ratio that is not a number is a low column, not a column that is missing from the map", () => {
    expect(columnHeight(Number.NaN, 1000)).toBe(500);
    expect(columnHeight(-1, 1000)).toBe(500);
  });
});

describe("buildAirLayers", () => {
  test("the ground goes below, and the columns of the stations above", () => {
    const layers = buildAirLayers(STATIONS, UNITS, vi.fn());

    expect(layers.map((layer) => layer.id)).toEqual(["units-ground", "stations"]);
  });

  test("without stations only the units are drawn, and without units only the stations", () => {
    expect(buildAirLayers(null, UNITS, vi.fn()).map((layer) => layer.id)).toEqual(["units-ground"]);
    expect(buildAirLayers(STATIONS, null, vi.fn()).map((layer) => layer.id)).toEqual(["stations"]);
    expect(buildAirLayers(null, null, vi.fn())).toEqual([]);
  });

  test("the ground of a municipality with stations is painted with the mean of their ratios, paler than the columns", () => {
    const painted: StationCollection = {
      ...STATIONS,
      features: [station("B1", "01001", 0.4), station("B2", "01001", 1.2), station("B3", "01002", 2)],
    };
    const [units] = buildAirLayers(painted, UNITS, vi.fn()).map(propsOf);
    const [a, b] = UNITS.features;

    expect(units.getFillColor(a)).toEqual([...ratioColor(0.8).slice(0, 3), FLAT_ALPHA]);
    expect(units.getFillColor(b)).toEqual([...ratioColor(2).slice(0, 3), FLAT_ALPHA]);
    expect(FLAT_ALPHA).toBeLessThan(ratioColor(0.8)[3]);
  });

  test("a municipality without a station, or whose stations have no ratio, stays the dark one: it is not painted with a value that nobody measured", () => {
    const painted: StationCollection = { ...STATIONS, features: [station("B1", "01001", 0.4), station("B2", "01002", null)] };
    const [units] = buildAirLayers(painted, UNITS, vi.fn()).map(propsOf);
    const [, noRatio, noStation] = UNITS.features;

    expect(units.getFillColor(noRatio)).toEqual(NEUTRAL_UNIT);
    expect(units.getFillColor(noStation)).toEqual(NEUTRAL_UNIT);
  });

  test("without stations (loading, or an error) every unit is the dark one", () => {
    const [units] = buildAirLayers(null, UNITS, vi.fn()).map(propsOf);

    for (const feature of UNITS.features) expect(units.getFillColor(feature)).toEqual(NEUTRAL_UNIT);
  });

  test("a district or a territory has no mean here: only the municipalities are painted", () => {
    const painted: StationCollection = { ...STATIONS, features: [station("B1", "48020", 1)] };
    const [units] = buildAirLayers(painted, UNITS, vi.fn()).map(propsOf);
    const territory = { ...UNITS.features[0], properties: { ...UNITS.features[0].properties, code: "48" } };

    expect(units.getFillColor(territory)).toEqual(NEUTRAL_UNIT);
  });

  test("the ground is painted again when the stations change (another pollutant)", () => {
    const first = buildAirLayers(STATIONS, UNITS, vi.fn()).map(propsOf)[0];
    const other = { ...STATIONS, pollutant: "O3" };
    const second = buildAirLayers(other, UNITS, vi.fn()).map(propsOf)[0];

    expect(first.updateTriggers.getFillColor).toEqual([STATIONS]);
    expect(second.updateTriggers.getFillColor).toEqual([other]);
  });

  test("the units can still be clicked, to open their panel", () => {
    const onUnit = vi.fn();
    const [units] = buildAirLayers(STATIONS, UNITS, onUnit).map(propsOf);

    expect(units.pickable).toBe(true);
    units.onClick({ object: UNITS.features[2] });
    units.onClick({ object: null });

    expect(onUnit).toHaveBeenCalledTimes(1);
    expect(onUnit).toHaveBeenCalledWith("01003");
  });

  test("a station is a 3D column in its position, and a station without position is not drawn", () => {
    const [, stations] = buildAirLayers(STATIONS, UNITS, vi.fn()).map(propsOf);

    expect(stations.extruded).toBe(true);
    expect(stations.diskResolution).toBe(6); // six sides, like the hexagons of the other map
    expect(stations.data.map((f: StationFeature) => f.properties.code)).toEqual(["A1", "A2", "A4"]);
    expect(stations.getPosition(STATIONS.features[1])).toEqual([-2.8, 43.3]);
  });

  test.each([
    ["no coordinates", []],
    ["one coordinate", [-2.9]],
    ["text", ["-2.9", "43.2"]],
    ["not numbers", [Number.NaN, 43.2]],
    ["infinity", [-2.9, Number.POSITIVE_INFINITY]],
    ["null", [null, null]],
  ])("a station with a position of %s is not drawn, and does not take the others down", (_name, coordinates) => {
    const broken = { ...station("A9", "48020", 1), geometry: { type: "Point", coordinates: coordinates as number[] } };
    const [, stations] = buildAirLayers({ ...STATIONS, features: [...STATIONS.features, broken] }, UNITS, vi.fn()).map(propsOf);

    expect(stations.data.map((f: StationFeature) => f.properties.code)).toEqual(["A1", "A2", "A4"]);
  });

  test("a position that is not a list is not drawn either", () => {
    const broken = { ...station("A9", "48020", 1), geometry: { type: "Point", coordinates: "x" as unknown as number[] } };
    const [, stations] = buildAirLayers({ ...STATIONS, features: [broken] }, UNITS, vi.fn()).map(propsOf);

    expect(stations.data).toEqual([]);
  });

  test("the colour and the height of a column follow the ratio of its station", () => {
    const [, stations] = buildAirLayers(STATIONS, UNITS, vi.fn(), 1000).map(propsOf);
    const [low, high, none] = [STATIONS.features[0], STATIONS.features[1], STATIONS.features[3]];

    expect(stations.getFillColor(low)).toEqual(ratioColor(0.4));
    expect(stations.getFillColor(high)).toEqual(ratioColor(1.2));
    expect(stations.getFillColor(none)).toEqual(ratioColor(null));
    expect(stations.getElevation(high)).toBe(columnHeight(1.2, 1000));
    expect(stations.getElevation(none)).toBe(columnHeight(null, 1000));
  });

  test("the radius is the one that is given (the biggest if none), and the heights are made again when it changes", () => {
    const [, big] = buildAirLayers(STATIONS, UNITS, vi.fn()).map(propsOf);
    const [, small] = buildAirLayers(STATIONS, UNITS, vi.fn(), 300).map(propsOf);

    expect(big.radius).toBe(1500);
    expect(small.radius).toBe(300);
    expect(small.getElevation(STATIONS.features[1])).toBe(columnHeight(1.2, 300));
    expect(small.updateTriggers.getElevation).toEqual([300]);
  });

  test("clicking a station opens the panel of its municipality with that station shown, and clicking nothing does nothing", () => {
    const onUnit = vi.fn();
    const [, stations] = buildAirLayers(STATIONS, UNITS, onUnit).map(propsOf);

    expect(stations.pickable).toBe(true);
    stations.onClick({ object: STATIONS.features[3] });
    stations.onClick({ object: null });

    expect(onUnit).toHaveBeenCalledTimes(1);
    expect(onUnit).toHaveBeenCalledWith("20069", STATIONS.features[3].properties.id);
  });

  test("clicking a unit tells only its code: no station is open then", () => {
    const onUnit = vi.fn();
    const [units] = buildAirLayers(STATIONS, UNITS, onUnit).map(propsOf);

    units.onClick({ object: UNITS.features[0] });

    expect(onUnit.mock.calls[0]).toEqual(["01001"]);
  });
});
