import { afterEach, describe, expect, test } from "vitest";
import { formatMeasure } from "../src/format";
import { setLanguage, texts } from "../src/i18n";
import { seriesPoints, seriesRange, seriesSection, type SeriesFn } from "../src/series";
import type { StationReading, StationSeries, UnitStation } from "../src/types";

const NOW = new Date("2026-11-25T14:20:00Z");

const reading = (pollutant: string, guideline: number | null, period: "24h" | "8h" | null = "24h"): StationReading => ({
  pollutant, ts: "2026-11-25T13:00:00Z", value: 20, unit: "µg/m3", who_period: guideline === null ? null : period,
  who_guideline_ugm3: guideline, who_mean_ugm3: 15, who_samples: 24, who_ratio: 0.6,
});

const STATION: UnitStation = {
  id: 7, code: "BI1", name: "Mazarredo", geometry: null, meteo_only: false, recent: true,
  readings: [reading("NO", null, null), reading("NO2", 25)],
};

const answer = (points: StationSeries["points"]): StationSeries => ({
  attribution: "x", station: { id: 7, code: "BI1", name: "Mazarredo" }, pollutant: "NO2",
  interval: "day", unit: "µg/m3", from: "a", to: "b", points,
});

afterEach(() => setLanguage("en"));

describe("the series of a station", () => {
  test("24 hours are the values of each hour; 7 and 30 days, the mean of each UTC day", () => {
    expect(seriesRange("day", NOW)).toEqual({ from: "2026-11-24T14:00:00.000Z", to: NOW.toISOString(), interval: "hour" });
    expect(seriesRange("week", NOW)).toEqual({ from: "2026-11-19T00:00:00.000Z", to: NOW.toISOString(), interval: "day" });
    expect(seriesRange("month", NOW).from).toBe("2026-10-27T00:00:00.000Z");
  });

  test("a day with fewer than 18 hours is marked as partial", () => {
    const points = seriesPoints(answer([
      { ts: "2026-11-24T00:00:00Z", value: 30, hours: 24, coverage_ok: true },
      { ts: "2026-11-25T00:00:00Z", value: 12, hours: 14, coverage_ok: false },
    ]));

    expect(points.map((point) => point.partial)).toEqual([false, true]);
  });

  test("opening it asks the series of the pollutant of the map for 24 hours, and writes it as a table too", async () => {
    const asked: Parameters<SeriesFn>[] = [];
    const section = seriesSection(STATION, new Map(), "NO2", async (...args) => {
      asked.push(args);
      return answer([{ ts: "2026-11-25T12:00:00Z", value: 31 }, { ts: "2026-11-25T13:00:00Z", value: 28 }]);
    }, () => NOW);

    document.body.append(section);
    section.querySelector<HTMLButtonElement>("button.open-series")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    // The keyboard goes on to the choice of the pollutant.
    expect(document.activeElement).toBe(section.querySelector("select.pollutant"));
    section.remove();
    expect(asked[0][0]).toBe(7);
    expect(asked[0][1]).toBe("NO2");
    expect(asked[0][2].interval).toBe("hour");
    expect(section.querySelectorAll(".visually-hidden tbody tr")).toHaveLength(2);
    expect(section.textContent).toContain(texts().seriesGuideline("24h", formatMeasure(25, "µg/m3")));
  });

  test("a pollutant without a WHO guideline says so, and the series of another period can be chosen", async () => {
    const asked: Parameters<SeriesFn>[] = [];
    const section = seriesSection(STATION, new Map(), "CO", async (...args) => {
      asked.push(args);
      return answer([]);
    }, () => NOW);
    section.querySelector<HTMLButtonElement>("button.open-series")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    // The map shows CO, which the station does not measure: the first of its pollutants.
    expect(asked[0][1]).toBe("NO");
    expect(section.textContent).toContain(texts().seriesNoGuideline);
    const period = section.querySelector<HTMLSelectElement>("select.period")!;
    period.value = "month";
    period.dispatchEvent(new Event("change"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(asked[1][2].interval).toBe("day");
    expect(section.textContent).toContain(texts().seriesEmpty);
  });

  test("a failure says so and leaves nothing of the series before", async () => {
    let fail = false;
    const section = seriesSection(STATION, new Map(), "NO2", async () => {
      if (fail) throw new Error("down");
      return answer([{ ts: "2026-11-25T12:00:00Z", value: 31 }]);
    }, () => NOW);
    section.querySelector<HTMLButtonElement>("button.open-series")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    fail = true;
    const period = section.querySelector<HTMLSelectElement>("select.period")!;
    period.value = "week";
    period.dispatchEvent(new Event("change"));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(section.querySelector("[role=status]")!.textContent).toBe(texts().serviceUnavailable);
    expect(section.querySelectorAll(".visually-hidden tbody tr")).toHaveLength(0);
  });

  test("by the day, an 8-hour guideline (ozone) is not drawn against the mean of the day, and says why", async () => {
    const ozone: UnitStation = { ...STATION, readings: [reading("O3", 100, "8h")] };
    const section = seriesSection(ozone, new Map(), "O3", async () => answer([{ ts: "2026-11-24T00:00:00Z", value: 40 }]), () => NOW);
    section.querySelector<HTMLButtonElement>("button.open-series")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(section.textContent).not.toContain(texts().seriesEightHourDaily);

    const period = section.querySelector<HTMLSelectElement>("select.period")!;
    period.value = "week";
    period.dispatchEvent(new Event("change"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(section.textContent).toContain(texts().seriesEightHourDaily);
  });
});
