import { describe, expect, test } from "vitest";
import { HEXAGON_MAX_RADIUS, HEXAGON_MIN_RADIUS, hexRadiusForZoom } from "../src/hexagons";

describe("hexRadiusForZoom", () => {
  test.each([6.5, 7, 7.5, 8, 8.2])("looking at the whole country (zoom %f) the hexagons are the biggest ones", (zoom) => {
    expect(hexRadiusForZoom(zoom)).toBe(HEXAGON_MAX_RADIUS);
  });

  test("the closer the map, the smaller the hexagons, never bigger", () => {
    let previous = Infinity;
    for (let zoom = 6; zoom <= 14; zoom += 0.1) {
      const radius = hexRadiusForZoom(zoom);
      expect(radius).toBeLessThanOrEqual(previous);
      previous = radius;
    }
    expect(hexRadiusForZoom(11)).toBeLessThan(hexRadiusForZoom(9));
  });

  test("close to a town a hexagon is smaller than a municipality, which is a few kilometres wide", () => {
    // A hexagon is twice its radius wide. The smallest municipalities are about 1 km across.
    expect(hexRadiusForZoom(11) * 2).toBeLessThan(1000);
    expect(hexRadiusForZoom(12) * 2).toBeLessThan(500);
  });

  test("but not tiny: a hexagon is at least some 20 pixels wide on the screen while it is not at the minimum", () => {
    // Metres per pixel at the latitude of the Basque Country, 512 px tiles.
    const metresPerPixel = (zoom: number) => (40_075_016.686 * Math.cos((43 * Math.PI) / 180)) / (512 * 2 ** zoom);
    for (const zoom of [9.5, 10, 10.5, 11, 11.5, 12]) {
      expect((hexRadiusForZoom(zoom) * 2) / metresPerPixel(zoom)).toBeGreaterThan(20);
    }
  });

  test("they do not shrink for ever: they are never smaller than the minimum", () => {
    expect(hexRadiusForZoom(14)).toBe(HEXAGON_MIN_RADIUS);
    expect(hexRadiusForZoom(30)).toBe(HEXAGON_MIN_RADIUS);
  });

  test("the radius moves in steps, so that the points are not grouped again at every turn of the wheel", () => {
    expect(hexRadiusForZoom(10.4)).toBe(hexRadiusForZoom(10.5));
    expect(new Set([9, 9.1, 9.2, 9.3, 9.4].map(hexRadiusForZoom)).size).toBeLessThanOrEqual(2);
  });

  test("a zoom that is not a number keeps the biggest hexagons", () => {
    expect(hexRadiusForZoom(Number.NaN)).toBe(HEXAGON_MAX_RADIUS);
    expect(hexRadiusForZoom(-Infinity)).toBe(HEXAGON_MAX_RADIUS);
  });
});
