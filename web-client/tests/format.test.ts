import { describe, expect, test } from "vitest";
import {
  airPollutantName,
  errorText,
  formatArea,
  formatDensity,
  formatHour,
  formatMeasure,
  formatRatio,
  formatReadingRatio,
  formatTonnes,
  mapCaption,
} from "../src/format";
import type { StationReading } from "../src/types";

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

describe("the readings of the stations", () => {
  const reading = (overrides: Partial<StationReading> = {}): StationReading => ({
    pollutant: "NO2",
    ts: "2026-11-11T14:00:00.000Z",
    value: 19,
    unit: "µg/m3",
    who_period: "24h",
    who_guideline_ugm3: 25,
    who_mean_ugm3: 15,
    who_samples: 24,
    who_ratio: 0.6,
    ...overrides,
  });

  test.each([
    [19, "µg/m3", "19 µg/m³"],
    [0.2, "µg/m3", "0.2 µg/m³"],
    [0, "µg/m3", "0 µg/m³"],
    [1.234, "mg/m3", "1.23 mg/m³"],
    [7, "ng/m3", "7 ng/m³"],
  ])("a value of %s in %s is written %s, in the unit that the station gave", (value, unit, text) => {
    expect(formatMeasure(value, unit)).toBe(text);
  });

  test("an unknown unit is shown as it came", () => {
    expect(formatMeasure(5, "ppm")).toBe("5 ppm");
  });

  test("the hour is in UTC, which is what the API says, and says so", () => {
    expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("11 Nov, 14:00 UTC");
    expect(formatHour("2026-01-05T00:30:00.000Z")).toBe("5 Jan, 00:30 UTC");
  });

  test("the hour does not depend on the time zone of the machine", () => {
    const before = process.env.TZ;
    process.env.TZ = "Pacific/Auckland"; // 13 hours ahead: the day would change
    try {
      expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("11 Nov, 14:00 UTC");
    } finally {
      if (before === undefined) delete process.env.TZ;
      else process.env.TZ = before;
    }
  });

  test("the pollutants of the WHO have a name, and any other is shown by its code", () => {
    expect(airPollutantName("NO2")).toBe("Nitrogen dioxide");
    expect(airPollutantName("PM25")).toBe("Particles PM2.5"); // the code that the network uses
    expect(airPollutantName("O3")).toBe("Ozone");
    expect(airPollutantName("H2S")).toBe("H2S");
  });

  test("a pollutant that has no name here takes the one of the emissions of the unit, and ours come first", () => {
    const known = new Map([
      ["BENZENE", "Benzene"],
      ["NO2", "Something else"],
    ]);

    expect(airPollutantName("BENZENE", known)).toBe("Benzene");
    expect(airPollutantName("NO2", known)).toBe("Nitrogen dioxide");
    expect(airPollutantName("H2S", known)).toBe("H2S");
  });

  test("with a guideline and a complete day, the ratio is said as it is", () => {
    expect(formatReadingRatio(reading())).toBe("0.6× the WHO guideline");
  });

  test("a day with fewer than 24 values is said to be partial, with how many there are", () => {
    expect(formatReadingRatio(reading({ who_samples: 19 }))).toBe("0.6× the WHO guideline (19 of 24 hours)");
  });

  test("the running mean of 8 hours of ozone has no partial note: it has no count", () => {
    expect(formatReadingRatio(reading({ who_period: "8h", who_samples: null }))).toBe("0.6× the WHO guideline");
  });

  test("a guideline without a ratio says there is not enough data, and no guideline says that", () => {
    expect(formatReadingRatio(reading({ who_ratio: null, who_samples: 12 }))).toBe("Not enough data");
    expect(
      formatReadingRatio(reading({ who_period: null, who_guideline_ugm3: null, who_samples: null, who_ratio: null })),
    ).toBe("No WHO guideline");
  });
});
