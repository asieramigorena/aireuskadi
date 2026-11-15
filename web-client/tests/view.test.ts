import { describe, expect, test } from "vitest";
import { DEFAULT_VIEW, MAX_ZOOM, MIN_ZOOM, fitView } from "../src/view";

describe("fitView: the first view shows the whole Basque Country in whatever size the screen is", () => {
  test("on a laptop it is about the zoom that was chosen by eye", () => {
    const view = fitView(1360, 820);

    expect(view.zoom).toBeGreaterThan(8.2);
    expect(view.zoom).toBeLessThan(8.8);
    expect(view.longitude).toBeCloseTo(-2.6, 0);
    expect(view.latitude).toBeCloseTo(43, 0);
  });

  test("on a phone it is further away, because the same country has to fit in less width", () => {
    const phone = fitView(390, 800);

    expect(phone.zoom).toBeLessThan(7.8);
    expect(phone.zoom).toBeGreaterThanOrEqual(MIN_ZOOM);
    expect(phone.zoom).toBeLessThan(fitView(1360, 820).zoom);
  });

  test("the narrower or the shorter the screen, the further away", () => {
    expect(fitView(800, 820).zoom).toBeLessThan(fitView(1360, 820).zoom);
    expect(fitView(1360, 400).zoom).toBeLessThan(fitView(1360, 820).zoom);
    expect(fitView(360, 640).zoom).toBeLessThan(fitView(768, 1024).zoom);
  });

  test("it never goes outside the zoom that the map allows", () => {
    expect(fitView(60, 60).zoom).toBeGreaterThanOrEqual(MIN_ZOOM);
    expect(fitView(8000, 6000).zoom).toBeLessThan(MAX_ZOOM);
  });

  test("a container that has no size yet gets the default view and not a view made of NaN", () => {
    expect(fitView(0, 0)).toEqual(DEFAULT_VIEW);
    expect(fitView(0, 800)).toEqual(DEFAULT_VIEW);
    expect(fitView(Number.NaN, 800)).toEqual(DEFAULT_VIEW);
  });

  test("it is tilted like the first view always was, and the limits of the zoom travel with it", () => {
    const view = fitView(1360, 820);

    expect(view.pitch).toBe(40);
    expect(view.bearing).toBe(0);
    expect([view.minZoom, view.maxZoom]).toEqual([MIN_ZOOM, MAX_ZOOM]);
  });

  test("every number of the view is finite", () => {
    for (const [w, h] of [[320, 568], [390, 800], [768, 1024], [1024, 768], [1360, 820], [2560, 1440]]) {
      const view = fitView(w, h);
      for (const value of Object.values(view)) expect(Number.isFinite(value)).toBe(true);
    }
  });
});
