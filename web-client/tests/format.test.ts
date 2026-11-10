import { describe, expect, test } from "vitest";
import { errorText, formatArea, formatDensity, formatRatio, formatTonnes, mapCaption } from "../src/format";

describe("the numbers of the panel", () => {
  test("no data is said in words, and is not shown as a zero", () => {
    expect(formatTonnes(null)).toBe("No data");
    expect(formatDensity(null)).toBe("No data");
    expect(formatRatio(null)).toBe("No data");
  });

  test("a declared zero is a zero", () => {
    expect(formatTonnes(0)).toBe("0 t");
  });

  test.each([
    [250, "250 t"],
    [1234.5678, "1,230 t"],
    [0.000244, "0.000244 t"],
    [7909.1, "7,910 t"],
  ])("tonnes %s", (value, text) => {
    expect(formatTonnes(value)).toBe(text);
  });

  test("the density is in tonnes per square kilometre", () => {
    expect(formatDensity(0.5)).toBe("0.5 t/km²");
  });

  test("the ratio with the WHO guideline says how many times the guideline it is", () => {
    expect(formatRatio(2.5)).toBe("2.5× the WHO guideline");
  });

  test("the area", () => {
    expect(formatArea(57.2)).toBe("57.2 km²");
    expect(formatArea(2222.123)).toBe("2,220 km²");
  });
});

describe("the caption of the map", () => {
  test("says what is shown, with the label that the API does not give", () => {
    expect(mapCaption({ pollutant: "NOX", year: 2023 })).toBe("Declared industrial emissions of NOX in 2023");
  });
});

describe("what is said when a call fails", () => {
  test("a 422 means that there is nothing for that pollutant and year, and says what to do", () => {
    expect(errorText(422, "The request has invalid or missing parameters.")).toBe(
      "There is no data for that pollutant and year. Try another year.",
    );
  });

  test.each([
    [404, "Unit 99999 not found."],
    [502, "The service is not available right now."],
    [0, "The service cannot be reached."],
  ])("the other errors (%s) say what the call said", (status, message) => {
    expect(errorText(status, message)).toBe(message);
  });
});
