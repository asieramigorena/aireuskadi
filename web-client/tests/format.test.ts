import { afterEach, describe, expect, test } from "vitest";
import { setLanguage } from "../src/i18n";
import {
  AIR_POLLUTANT_CODES,
  airPollutantName,
  emissionName,
  errorText,
  formatArea,
  formatDensity,
  formatHour,
  formatMeasure,
  formatRatio,
  formatReadingRatio,
  formatTonnes,
  mapCaption,
  mapLabel,
} from "../src/format";
import type { StationReading } from "../src/types";

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
    expect(mapCaption({ view: "emissions", pollutant: "NOX", year: 2023 })).toBe("Declared industrial emissions of NOX in 2023");
  });
});

describe("what is said when a call fails", () => {
  test.each([
    [422, "There is no data for that pollutant and year. Try another year."],
    [404, "That page or unit does not exist."],
    [0, "The service cannot be reached."],
    [502, "The service is not available right now."],
    [504, "The service is not available right now."],
    [500, "The service is not available right now."],
  ])("an error %s is said in words: %s", (status, text) => {
    expect(errorText(status)).toBe(text);
  });
});

describe("the two maps", () => {
  test("the caption of the air quality says that it is the latest value, of which pollutant, and against what", () => {
    expect(mapCaption({ view: "air", pollutant: "NO2", year: 2023 })).toBe(
      "Latest air quality: nitrogen dioxide, against the WHO guideline",
    );
    expect(mapCaption({ view: "air", pollutant: "PM25", year: 2023 })).toBe(
      "Latest air quality: particles PM2.5, against the WHO guideline",
    );
  });

  test("a pollutant without a name here is said by its code, and the year of the emissions is not in this caption", () => {
    expect(mapCaption({ view: "air", pollutant: "H2S", year: 1999 })).toBe(
      "Latest air quality: H2S, against the WHO guideline",
    );
  });

  test("the label of the map for whoever cannot see it says which map it is", () => {
    expect(mapLabel("emissions")).toBe("3D map of the declared industrial emissions of the Basque Country");
    expect(mapLabel("air")).toBe("3D map of the latest air quality measured at the stations of the Basque Country");
  });

  test("the pollutants that the selector offers are the ones that have a guideline, in an order that is read", () => {
    expect(AIR_POLLUTANT_CODES).toEqual(["NO2", "PM25", "PM10", "O3", "SO2", "CO"]);
    for (const code of AIR_POLLUTANT_CODES) expect(airPollutantName(code)).not.toBe(code);
  });
});

describe("the readings of the stations", () => {
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

// --- the other languages ------------------------------------------------------------------------

afterEach(() => setLanguage("en"));

describe("the numbers, written by the dictionary and not by the browser", () => {
  test("English: a point for the decimals, a comma from four digits", () => {
    expect(formatTonnes(1234.5678)).toBe("1,230 t");
    expect(formatTonnes(243000)).toBe("243,000 t");
    expect(formatTonnes(0.000244)).toBe("0.000244 t");
    expect(formatArea(40.594)).toBe("40.6 km²");
  });

  test("Spanish: a comma for the decimals, a point from five digits (four are left whole)", () => {
    setLanguage("es");

    expect(formatTonnes(1234.5678)).toBe("1230 t");
    expect(formatTonnes(12345)).toBe("12.300 t");
    expect(formatTonnes(243000)).toBe("243.000 t");
    expect(formatTonnes(0.000244)).toBe("0,000244 t");
    expect(formatArea(40.594)).toBe("40,6 km²");
  });

  test("Basque: a comma for the decimals, a point from four digits", () => {
    setLanguage("eu");

    expect(formatTonnes(1234.5678)).toBe("1.230 t");
    expect(formatTonnes(243000)).toBe("243.000 t");
    expect(formatTonnes(0.000244)).toBe("0,000244 t");
    expect(formatArea(40.594)).toBe("40,6 km²");
  });

  test("a number that is zero, and one that is big, are written whole", () => {
    expect(formatTonnes(0)).toBe("0 t");
    setLanguage("eu");
    expect(formatTonnes(0)).toBe("0 t");
    expect(formatTonnes(1234567)).toBe("1.230.000 t");
  });

  test("never in the notation of the exponents, however small or big", () => {
    expect(formatTonnes(0.00000123)).toBe("0.00000123 t");
    expect(formatTonnes(123456789012)).toBe("123,000,000,000 t");
  });
});

describe("the hour, written by the dictionary and not by the browser", () => {
  test("English, Spanish and Basque, with the month of each", () => {
    expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("11 Nov, 14:00 UTC");
    setLanguage("es");
    expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("11 nov, 14:00 UTC");
    setLanguage("eu");
    expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("aza. 11, 14:00 UTC");
  });

  test("all the months, in each language", () => {
    const first = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    first.forEach((month, index) => {
      const day = `2026-${String(index + 1).padStart(2, "0")}-05T09:05:00.000Z`;
      expect(formatHour(day)).toBe(`5 ${month}, 09:05 UTC`);
    });
  });

  test("the month and the day are the ones of UTC, also at the end of the month with the clock of the machine a day ahead", () => {
    const before = process.env.TZ;
    process.env.TZ = "Pacific/Auckland"; // 13 hours ahead: it is already the 1st of January there
    try {
      expect(formatHour("2026-12-31T23:30:00.000Z")).toBe("31 Dec, 23:30 UTC");
    } finally {
      if (before === undefined) delete process.env.TZ;
      else process.env.TZ = before;
    }
  });

  test("midnight and the last minute of the day have two digits, and a time that is not one throws, as before", () => {
    expect(formatHour("2026-01-05T00:00:00.000Z")).toBe("5 Jan, 00:00 UTC");
    expect(formatHour("2026-01-05T23:59:59.000Z")).toBe("5 Jan, 23:59 UTC");
    expect(() => formatHour("garbage")).toThrow(RangeError);
  });
});

describe("in Spanish", () => {
  test("the numbers have a comma, and the phrases are Spanish", () => {
    setLanguage("es");

    expect(formatRatio(2.5)).toBe("2,5× el valor guía de la OMS");
    expect(formatTonnes(250)).toBe("250 t");
    expect(formatTonnes(0.000244)).toBe("0,000244 t");
    expect(formatTonnes(null)).toBe("Sin datos");
    expect(formatDensity(0.5)).toBe("0,5 t/km²");
    expect(formatArea(57.2)).toBe("57,2 km²");
  });

  test("the time has the month in Spanish, and is still UTC whatever the time zone of the machine is", () => {
    setLanguage("es");
    const before = process.env.TZ;
    process.env.TZ = "Pacific/Auckland";
    try {
      expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("11 nov, 14:00 UTC");
    } finally {
      if (before === undefined) delete process.env.TZ;
      else process.env.TZ = before;
    }
  });

  test("the comparison with the guideline, in its three forms", () => {
    setLanguage("es");

    expect(formatReadingRatio(reading())).toBe("0,6× el valor guía de la OMS");
    expect(formatReadingRatio(reading({ who_samples: 19 }))).toBe("0,6× el valor guía de la OMS (19 de 24 horas)");
    expect(formatReadingRatio(reading({ who_ratio: null, who_samples: 12 }))).toBe("Datos insuficientes");
    expect(
      formatReadingRatio(reading({ who_period: null, who_guideline_ugm3: null, who_samples: null, who_ratio: null })),
    ).toBe("Sin valor guía de la OMS");
  });

  test("the captions and the label of the map", () => {
    setLanguage("es");

    expect(mapCaption({ view: "emissions", pollutant: "NOX", year: 2023 })).toBe(
      "Emisiones industriales declaradas de NOX en 2023",
    );
    expect(mapCaption({ view: "air", pollutant: "NO2", year: 2023 })).toBe(
      "Calidad del aire más reciente: dióxido de nitrógeno, frente al valor guía de la OMS",
    );
    expect(mapLabel("air")).toContain("Mapa 3D de la calidad del aire");
  });

  test("the errors", () => {
    setLanguage("es");

    expect(errorText(422)).toBe("No hay datos para ese contaminante y año. Prueba con otro año.");
    expect(errorText(503)).toBe("El servicio no está disponible en este momento.");
  });
});

describe("in Basque", () => {
  test("the numbers have a comma, and the phrases are Basque", () => {
    setLanguage("eu");

    expect(formatRatio(2.5)).toBe("OMEren gidalerroaren 2,5×");
    expect(formatTonnes(250)).toBe("250 t");
    expect(formatTonnes(null)).toBe("Daturik ez");
    expect(formatDensity(0.5)).toBe("0,5 t/km²");
  });

  test("the time puts the month first, in Basque, and is UTC", () => {
    setLanguage("eu");

    expect(formatHour("2026-11-11T14:00:00.000Z")).toBe("aza. 11, 14:00 UTC");
  });

  test("the comparison with the guideline, in its three forms", () => {
    setLanguage("eu");

    expect(formatReadingRatio(reading())).toBe("OMEren gidalerroaren 0,6×");
    expect(formatReadingRatio(reading({ who_samples: 19 }))).toBe("OMEren gidalerroaren 0,6× (24 orduetatik 19)");
    expect(formatReadingRatio(reading({ who_ratio: null, who_samples: 12 }))).toBe("Ez dago datu nahikorik");
    expect(
      formatReadingRatio(reading({ who_period: null, who_guideline_ugm3: null, who_samples: null, who_ratio: null })),
    ).toBe("OMEren gidalerrorik ez");
  });

  test("the caption keeps a name that starts with the letters of a formula as it is, and lowers the others", () => {
    setLanguage("eu");

    expect(mapCaption({ view: "air", pollutant: "NO2", year: 2023 })).toBe(
      "Azken aire kalitatea: nitrogeno dioxidoa, OMEren gidalerroarekin alderatuta",
    );
    expect(mapCaption({ view: "air", pollutant: "PM25", year: 2023 })).toBe(
      "Azken aire kalitatea: PM2,5 partikulak, OMEren gidalerroarekin alderatuta",
    );
  });

  test("the errors", () => {
    setLanguage("eu");

    expect(errorText(422)).toBe("Ez dago daturik kutsatzaile eta urte horretarako. Saiatu beste urte batekin.");
    expect(errorText(0)).toBe("Ezin da zerbitzuarekin konektatu.");
  });
});

describe("the names of the pollutants follow the language", () => {
  test("those of the air quality, with the names of the card as a fallback and the code at last", () => {
    setLanguage("es");
    expect(airPollutantName("NO2")).toBe("Dióxido de nitrógeno");
    expect(airPollutantName("H2S", new Map([["H2S", "Sulfuro"]]))).toBe("Sulfuro");
    expect(airPollutantName("ZZ")).toBe("ZZ");

    setLanguage("eu");
    expect(airPollutantName("NO2")).toBe("Nitrogeno dioxidoa");
    expect(airPollutantName("PM25")).toBe("PM2,5 partikulak");
  });

  test("those of the emissions: the name of the language, and the one of the API where the language has none", () => {
    expect(emissionName("NOX", "Oxides of nitrogen (NOx)")).toBe("Oxides of nitrogen (NOx)");

    setLanguage("es");
    expect(emissionName("NOX", "Oxides of nitrogen (NOx)")).toBe("Óxidos de nitrógeno (NOx)");
    expect(emissionName("XYZ", "A new pollutant")).toBe("A new pollutant");

    setLanguage("eu");
    expect(emissionName("NOX", "Oxides of nitrogen (NOx)")).toBe("Nitrogeno oxidoak (NOx)");
  });

  test("a name that is the name of something that every object has does not find a text", () => {
    setLanguage("es");

    expect(emissionName("toString", "From the API")).toBe("From the API");
    expect(emissionName("constructor", "From the API")).toBe("From the API");
  });

  test("changing the language changes what is written the next time, with nothing to rebuild", () => {
    expect(formatRatio(1)).toBe("1× the WHO guideline");
    setLanguage("es");
    expect(formatRatio(1)).toBe("1× el valor guía de la OMS");
    setLanguage("eu");
    expect(formatRatio(1)).toBe("OMEren gidalerroaren 1×");
  });
});
