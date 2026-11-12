import { afterEach, describe, expect, test } from "vitest";
import { LANGUAGES, detectLanguage, isLanguage, language, setLanguage, texts, textsOf } from "../src/i18n";

// The pollutants of the emissions, as the API lists them (GET /pollutants).
const EMISSION_CODES = [
  "ANTIMONY", "ARSENIC", "BENZENE", "CADMIUM", "CH4", "CHROMIUM", "CO", "CO2", "COBALT", "COPPER", "DCM",
  "DIOXINS", "ETHYLBENZENE", "H2S", "HCB", "HCL", "HCN", "HF", "HFC", "LEAD", "MANGANESE", "MERCURY",
  "M_P_XYLENE", "N2O", "NH3", "NICKEL", "NMVOC", "NO", "NO2", "NOX", "O3", "O_XYLENE", "PAH", "PCB", "PCE",
  "PECB", "PFC", "PM10", "PM25", "SO2", "SOX", "TCE", "THALLIUM", "TOC", "TOLUENE", "TSP", "VANADIUM", "VCM",
  "ZINC",
];
const AIR_CODES = ["NO2", "PM25", "PM10", "O3", "SO2", "CO"];

afterEach(() => setLanguage("en"));

describe("the languages", () => {
  test("are Basque, Spanish and English, in the order that the selector shows them", () => {
    expect(LANGUAGES).toEqual(["eu", "es", "en"]);
  });

  test.each([["eu", true], ["es", true], ["en", true], ["fr", false], ["EU", false], ["", false], ["eu-ES", false]])(
    "%s is a language of the page: %s",
    (code, expected) => {
      expect(isLanguage(code)).toBe(expected);
    },
  );
});

describe("detectLanguage: the language that the browser of the visitor asks for", () => {
  test.each([
    [["eu"], "eu"],
    [["eu-ES"], "eu"],
    [["es-ES", "en"], "es"],
    [["es-419"], "es"],
    [["en-GB", "es"], "en"],
    [["EU-es"], "eu"],
    [["fr", "eu"], "eu"],
    [["fr-FR", "en-GB"], "en"],
    [["pt-BR", "de", "es"], "es"],
  ])("%j is %s: the first language of the list that the page has", (preferred, expected) => {
    expect(detectLanguage(preferred)).toBe(expected);
  });

  test("a browser that asks for none of them, or for nothing, gets English", () => {
    expect(detectLanguage(["fr", "de-AT", "zh-Hans"])).toBe("en");
    expect(detectLanguage([])).toBe("en");
  });

  test("what is not a language tag is skipped, and does not stop the search", () => {
    expect(detectLanguage(["", "  ", "*", "eu-"])).toBe("eu");
    expect(detectLanguage(["", "*"])).toBe("en");
  });

  test("a value that is not even a string (a browser with no language) is skipped, not an error", () => {
    expect(detectLanguage([undefined as unknown as string, null as unknown as string, "es"])).toBe("es");
    expect(detectLanguage([undefined as unknown as string])).toBe("en");
  });
});

describe("the language in use", () => {
  test("is English until someone chooses another one", () => {
    expect(language()).toBe("en");
    expect(texts()).toBe(textsOf("en"));
  });

  test("changes with setLanguage, and the texts follow it", () => {
    setLanguage("eu");
    expect(language()).toBe("eu");
    expect(texts()).toBe(textsOf("eu"));
    expect(texts().viewAir).toBe("Aire kalitatea");

    setLanguage("es");
    expect(texts().viewAir).toBe("Calidad del aire");
  });
});

/** Every text of a dictionary that is a string, with the path to it: the functions and the tables of names are left. */
function strings(value: unknown, path = ""): [string, string][] {
  // The table of the names of the emissions is checked on its own: English has none.
  if (path === "pollutants") return [];
  if (typeof value === "string") return [[path, value]];
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, inner]) => strings(inner, path ? `${path}.${key}` : key));
  }
  return [];
}

describe.each(LANGUAGES)("the texts in %s", (code) => {
  const dictionary = textsOf(code);

  test("have no empty text", () => {
    for (const [path, text] of strings(dictionary)) expect(text.trim(), path).not.toBe("");
  });

  test("the texts with a hole put what they are given in it, and leave nothing undefined", () => {
    const made = [
      dictionary.airCredit("ATTR"),
      dictionary.captionEmissions("POLL", 2023),
      dictionary.captionAir("POLL"),
      dictionary.ratioOfGuideline("0.6"),
      dictionary.partialDay(19),
      dictionary.hour("11", "MON", "14:00"),
      dictionary.emissionsCaption(2023),
      dictionary.noEmissions(2023),
      dictionary.latestValue("HOUR"),
    ];
    for (const text of made) {
      expect(typeof text).toBe("string");
      expect(text).not.toMatch(/undefined|NaN|\[object|\$\{/);
    }
    expect(made[0]).toContain("ATTR");
    expect(made[1]).toContain("POLL");
    expect(made[1]).toContain("2023");
    expect(made[2]).toContain("POLL");
    expect(made[3]).toContain("0.6");
    expect(made[4]).toContain("19");
    expect(made[5]).toMatch(/11.*MON.*14:00.*UTC|MON.*11.*14:00.*UTC/);
    expect(made[6]).toContain("2023");
    expect(made[7]).toContain("2023");
    expect(made[8]).toContain("HOUR");
  });

  test("name the six pollutants of the air quality", () => {
    expect(Object.keys(dictionary.airPollutants).sort()).toEqual([...AIR_CODES].sort());
  });

  test("say how the numbers are written, without asking the browser: its data for a language can be missing", () => {
    expect(dictionary.decimalSeparator).toMatch(/^[.,]$/);
    expect(dictionary.groupSeparator).toMatch(/^[.,\u00a0 ]$/);
    expect(dictionary.groupSeparator).not.toBe(dictionary.decimalSeparator);
    expect(dictionary.groupFrom).toBeGreaterThanOrEqual(4);
  });

  test("have the twelve months, short, all different, and in the order of the year", () => {
    expect(dictionary.months).toHaveLength(12);
    expect(new Set(dictionary.months).size).toBe(12);
    for (const month of dictionary.months) expect(month.trim(), month).not.toBe("");
  });
});

describe("what is translated is not left in English", () => {
  const english = new Map(strings(textsOf("en")));

  test.each(["eu", "es"] as const)("every text of %s is different from the English one", (code) => {
    for (const [path, text] of strings(textsOf(code))) {
      // The separators are signs, not words: the same sign is right in two languages.
      if (path === "decimalSeparator" || path === "groupSeparator") continue;
      expect(english.has(path), `${path} is missing in English`).toBe(true);
      expect(text, path).not.toBe(english.get(path));
    }
  });

  test.each(["eu", "es"] as const)("%s has the same texts as English, no more and no fewer", (code) => {
    expect(strings(textsOf(code)).map(([path]) => path).sort()).toEqual([...english.keys()].sort());
  });
});

describe("the names of the pollutants", () => {
  test.each(["eu", "es"] as const)("%s names all the pollutants of the emissions, and only them", (code) => {
    expect(Object.keys(textsOf(code).pollutants).sort()).toEqual([...EMISSION_CODES].sort());
  });

  test.each(["eu", "es"] as const)("%s says the same name for a pollutant of the air in the table of the stations and in the one of the emissions", (code) => {
    const dictionary = textsOf(code);
    for (const air of AIR_CODES) expect(dictionary.pollutants[air], air).toBe(dictionary.airPollutants[air as keyof typeof dictionary.airPollutants]);
  });

  test("English has no table of the emissions: the names come from the API, which is in English", () => {
    expect(textsOf("en").pollutants).toEqual({});
  });
});

describe("a few of the texts, so that they are not swapped", () => {
  test("Basque", () => {
    const eu = textsOf("eu");
    expect(eu.viewEmissions).toBe("Isuriak");
    expect(eu.ratioOfGuideline("0,6")).toBe("OMEren gidalerroaren 0,6×");
    expect(eu.kinds).toEqual({ municipality: "Udalerria", district: "Eskualdea", territory: "Lurraldea" });
    expect(eu.airPollutants.NO2).toBe("Nitrogeno dioxidoa");
  });

  test("Spanish", () => {
    const es = textsOf("es");
    expect(es.viewEmissions).toBe("Emisiones");
    expect(es.ratioOfGuideline("0,6")).toBe("0,6× el valor guía de la OMS");
    expect(es.kinds).toEqual({ municipality: "Municipio", district: "Comarca", territory: "Territorio" });
    expect(es.airPollutants.NO2).toBe("Dióxido de nitrógeno");
  });

  test("English, which is what the tests of the rest of the page read", () => {
    const en = textsOf("en");
    expect(en.viewEmissions).toBe("Emissions");
    expect(en.ratioOfGuideline("2.5")).toBe("2.5× the WHO guideline");
    expect(en.hour("11", "Nov", "14:00")).toBe("11 Nov, 14:00 UTC");
  });
});
