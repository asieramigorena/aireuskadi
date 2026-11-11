// The layers of the map. The units are flat polygons painted by their density, and above them the
// hexagons of the facilities, in 3D: the taller and brighter, the more kilograms declared.
import { HexagonLayer } from "@deck.gl/aggregation-layers";
import type { Layer } from "@deck.gl/core";
import { GeoJsonLayer } from "@deck.gl/layers";
import { HEXAGON_MAX_RADIUS } from "./hexagons";
import { colorFor, maxDensity } from "./scale";
import type { Point, UnitCollection, UnitFeature } from "./types";

const HEXAGON_COLORS: [number, number, number][] = [
  [1, 152, 189],
  [73, 227, 206],
  [216, 254, 181],
  [254, 237, 177],
  [254, 173, 84],
  [209, 55, 78],
];

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
      new GeoJsonLayer<UnitFeature["properties"]>({
        id: "units",
        data: units as never,
        filled: true,
        stroked: true,
        getFillColor: (feature) => colorFor((feature as unknown as UnitFeature).properties.t_km2, max),
        getLineColor: [255, 255, 255, 70],
        lineWidthMinPixels: 0.5,
        // Clicking is for the units. The hexagons are above them but cannot be clicked, so that a
        // click on a column reaches the unit that is under it.
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        onClick: ({ object }) => {
          if (object) onUnit((object as unknown as UnitFeature).properties.code);
        },
        updateTriggers: { getFillColor: [max] },
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
