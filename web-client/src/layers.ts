// The layers of the two maps. Emissions: the units are flat polygons painted by their density, and
// above them the hexagons of the facilities, in 3D: the taller and brighter, the more kilograms
// declared. Air quality: the units are painted with the mean of the ratios of their stations (dark
// if they have none), and above them a 3D column in each station: the taller and redder, the closer
// its latest value is to the WHO guideline (or over it).
import { HexagonLayer } from "@deck.gl/aggregation-layers";
import type { Layer } from "@deck.gl/core";
import { ColumnLayer, GeoJsonLayer } from "@deck.gl/layers";
import { HEXAGON_MAX_RADIUS } from "./hexagons";
import { RATIO_MAX, type Color, colorFor, maxDensity, ratioColor } from "./scale";
import { meanRatioByMunicipality } from "./stations";
import type { Point, StationCollection, StationFeature, UnitCollection, UnitFeature } from "./types";

const HEXAGON_COLORS: [number, number, number][] = [
  [1, 152, 189],
  [73, 227, 206],
  [216, 254, 181],
  [254, 237, 177],
  [254, 173, 84],
  [209, 55, 78],
];

/** The units of the map of the air quality that no station says anything about: dark, so that the
 * columns are what is seen. */
export const NEUTRAL_UNIT: Color = [52, 68, 76, 210];

/** The ground of a municipality with stations has the colour of the scale, but paler than the
 * columns (which are 235 or more), so that the columns stay what is seen. */
export const FLAT_ALPHA = 170;

// The shortest column is half a radius (a station with no ratio, or at zero, is still seen) and the
// tallest eight: from twice the guideline up the column does not grow, as the colour does not change.
const SHORTEST_COLUMN = 0.5;
const TALLEST_COLUMN = 8;

/** How tall the column of a station is, in metres, for the radius of the columns. */
export function columnHeight(ratio: number | null, radius: number): number {
  if (ratio === null || !Number.isFinite(ratio)) return radius * SHORTEST_COLUMN;
  const share = Math.min(Math.max(ratio, 0), RATIO_MAX) / RATIO_MAX;
  return radius * (SHORTEST_COLUMN + (TALLEST_COLUMN - SHORTEST_COLUMN) * share);
}

/** A station that can be drawn: it has a position, two numbers. What the service sends is not
 * trusted so far that a position that is not one takes the whole map down. */
function hasPosition(station: StationFeature): boolean {
  const coordinates = station.geometry?.coordinates;
  return Array.isArray(coordinates) && coordinates.length >= 2 && coordinates.slice(0, 2).every(Number.isFinite);
}

/** The flat polygons of the units, which can be clicked to open the panel of the unit. */
function unitsLayer(
  id: string,
  units: UnitCollection,
  getFillColor: Color | ((feature: UnitFeature) => Color),
  onUnit: (code: string) => void,
  updateTriggers: Record<string, unknown[]> = {},
) {
  return new GeoJsonLayer<UnitFeature["properties"]>({
    id,
    data: units as never,
    filled: true,
    stroked: true,
    getFillColor: typeof getFillColor === "function" ? (feature) => getFillColor(feature as unknown as UnitFeature) : getFillColor,
    getLineColor: [255, 255, 255, 70],
    lineWidthMinPixels: 0.5,
    // Clicking is for the units. What is drawn above them (the hexagons) cannot be clicked, so that a
    // click on a column reaches the unit that is under it.
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 60],
    onClick: ({ object }) => {
      if (object) onUnit((object as unknown as UnitFeature).properties.code);
    },
    updateTriggers,
  });
}

export function buildLayers(
  points: Point[],
  units: UnitCollection | null,
  onUnit: (code: string) => void,
  hexRadius: number = HEXAGON_MAX_RADIUS,
): Layer[] {
  const layers: Layer[] = [];

  if (units) {
    const max = maxDensity(units.features);
    layers.push(
      unitsLayer("units", units, (feature) => colorFor(feature.properties.t_km2, max), onUnit, {
        getFillColor: [max],
      }),
    );
  }

  layers.push(
    new HexagonLayer<Point>({
      id: "hexagons",
      data: points,
      getPosition: (point) => [point[0], point[1]],
      getElevationWeight: (point) => point[2],
      getColorWeight: (point) => point[2],
      elevationAggregation: "SUM",
      colorAggregation: "SUM",
      extruded: true,
      radius: hexRadius,
      coverage: 0.85,
      // As tall as four radii: a smaller hexagon with a column as tall as a big one would be a needle.
      elevationRange: [0, hexRadius * 4],
      colorRange: HEXAGON_COLORS,
      upperPercentile: 100,
      pickable: false,
    }),
  );
  return layers;
}

/** The map of the air quality. A click on a station opens the panel of its municipality with that
 * station shown (`onUnit` gets its id); a click on a unit opens only its panel. */
export function buildAirLayers(
  stations: StationCollection | null,
  units: UnitCollection | null,
  onUnit: (code: string, station?: number) => void,
  radius: number = HEXAGON_MAX_RADIUS,
): Layer[] {
  const layers: Layer[] = [];
  if (units) {
    // Only the municipalities have stations: a district or a territory is never in this map.
    const means = stations ? meanRatioByMunicipality(stations.features) : new Map<string, number>();
    const ground = (feature: UnitFeature): Color => {
      const ratio = means.get(feature.properties.code);
      return ratio === undefined ? NEUTRAL_UNIT : [...ratioColor(ratio).slice(0, 3), FLAT_ALPHA] as Color;
    };
    layers.push(unitsLayer("units-ground", units, ground, (code) => onUnit(code), { getFillColor: [stations] }));
  }
  if (stations) {
    layers.push(
      new ColumnLayer<StationFeature>({
        id: "stations",
        // A station without a position has data but no place on the map.
        data: stations.features.filter(hasPosition),
        getPosition: (station) => station.geometry!.coordinates as [number, number],
        getFillColor: (station) => ratioColor(station.properties.who_ratio),
        getElevation: (station) => columnHeight(station.properties.who_ratio, radius),
        radius,
        // Six sides, like the hexagons of the other map.
        diskResolution: 6,
        extruded: true,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 90],
        onClick: ({ object }) => {
          if (object) onUnit(object.properties.municipality_code, object.properties.id);
        },
        updateTriggers: { getElevation: [radius] },
      }),
    );
  }
  return layers;
}
