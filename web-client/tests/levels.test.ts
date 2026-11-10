import { describe, expect, test } from "vitest";
import { levelForZoom } from "../src/levels";

describe("levelForZoom: the further away, the bigger the unit", () => {
  test.each([
    [0, "territory"],
    [6, "territory"],
    [7.59, "territory"],
    [7.6, "district"],
    [8.19, "district"],
    [8.2, "municipality"],
    [12, "municipality"],
    [22, "municipality"],
  ])("zoom %s is %s", (zoom, level) => {
    expect(levelForZoom(zoom)).toBe(level);
  });

  test("a zoom that is not a number is the most detailed level, which is the one that is always there", () => {
    expect(levelForZoom(Number.NaN)).toBe("municipality");
    expect(levelForZoom(Number.POSITIVE_INFINITY)).toBe("municipality");
  });
});
