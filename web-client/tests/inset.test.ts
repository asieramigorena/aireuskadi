import { describe, expect, test } from "vitest";
import { insetFor } from "../src/view";

const NONE = { top: 0, right: 0, bottom: 0, left: 0 };

describe("insetFor: how much of the map the panel covers, so that the map is centred in what is left", () => {
  test("without a panel nothing is covered", () => {
    expect(insetFor(null, 1360, 820)).toEqual(NONE);
  });

  test("a panel on the right covers that much of the width", () => {
    // 416 wide, 16 from the right edge.
    expect(insetFor({ left: 928, top: 16, width: 416, height: 788 }, 1360, 820)).toEqual({
      ...NONE,
      right: 1360 - 928,
    });
  });

  test("a sheet from the bottom, as wide as the screen, covers from its top to the bottom", () => {
    expect(insetFor({ left: 12, top: 560, width: 366, height: 250 }, 390, 844)).toEqual({
      ...NONE,
      bottom: 844 - 560,
    });
  });

  test("a panel on the left covers the left", () => {
    expect(insetFor({ left: 0, top: 0, width: 300, height: 800 }, 1360, 820)).toEqual({
      ...NONE,
      left: 300,
    });
  });

  test("never more than the screen has, and never a negative number", () => {
    const wide = insetFor({ left: -50, top: 0, width: 5000, height: 900 }, 1000, 800);
    for (const value of Object.values(wide)) {
      expect(value).toBeGreaterThanOrEqual(0);
    }
    expect(insetFor({ left: 900, top: 0, width: 500, height: 800 }, 1000, 800).right).toBe(100);
    expect(insetFor({ left: 12, top: 900, width: 366, height: 200 }, 390, 844).bottom).toBe(0);
  });

  test("a screen that has no size has nothing covered", () => {
    const panel = { left: 0, top: 0, width: 10, height: 10 };

    expect(insetFor(panel, 0, 0)).toEqual(NONE);
    expect(insetFor(panel, Number.NaN, 800)).toEqual(NONE);
    expect(insetFor(panel, 1000, Number.NaN)).toEqual(NONE);
  });

  test("a sheet that starts above the screen covers the whole height and not more", () => {
    expect(insetFor({ left: 12, top: -50, width: 366, height: 200 }, 390, 844).bottom).toBe(844);
  });
});
