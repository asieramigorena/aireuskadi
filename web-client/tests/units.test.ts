import { describe, expect, test } from "vitest";
import type { BoundaryCollection, UnitIndicators } from "../src/types";
import { withIndicators } from "../src/units";

const square = { type: "MultiPolygon", coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 0]]]] };

const boundaries: BoundaryCollection = {
  type: "FeatureCollection",
  attribution: "GeoEuskadi / Gobierno Vasco, CC BY 4.0, simplified",
  features: [
    { type: "Feature", geometry: square, properties: { code: "48020", name: "Bilbao" } },
    { type: "Feature", geometry: null, properties: { code: "01059", name: "Vitoria-Gasteiz" } },
  ],
};

const bilbao: UnitIndicators = { code: "48020", name: "Bilbao", declared_t: 12, t_km2: 0.3, who_ratio: 1.2 };

describe("the units of the map: the boundaries, once, and the indicators of the pollutant and the year", () => {
  test("each boundary takes the indicators of its code", () => {
    const units = withIndicators(boundaries, [bilbao]);

    expect(units.features[0]).toEqual({
      type: "Feature",
      geometry: square,
      properties: { code: "48020", name: "Bilbao", declared_t: 12, t_km2: 0.3, who_ratio: 1.2 },
    });
  });

  test("a unit that has no indicators has no data, not a zero", () => {
    const units = withIndicators(boundaries, [bilbao]);

    expect(units.features[1].properties).toEqual({
      code: "01059",
      name: "Vitoria-Gasteiz",
      declared_t: null,
      t_km2: null,
      who_ratio: null,
    });
  });

  test("without indicators (the map of the air quality) every unit is there, with no data", () => {
    const units = withIndicators(boundaries, null);

    expect(units.features.map((feature) => feature.properties.declared_t)).toEqual([null, null]);
    expect(units.features.map((feature) => feature.geometry)).toEqual([square, null]);
  });

  test("the credit of the boundaries is kept", () => {
    expect(withIndicators(boundaries, []).attribution).toBe(boundaries.attribution);
  });

  test("an indicator of a code that has no boundary is not drawn anywhere", () => {
    const units = withIndicators(boundaries, [{ ...bilbao, code: "99999" }]);

    expect(units.features.map((feature) => feature.properties.code)).toEqual(["48020", "01059"]);
    expect(units.features[0].properties.declared_t).toBeNull();
  });

  test("the name is the one of the boundary, the indicators only bring numbers", () => {
    const units = withIndicators(boundaries, [{ ...bilbao, name: "BILBAO" }]);

    expect(units.features[0].properties.name).toBe("Bilbao");
  });
});

