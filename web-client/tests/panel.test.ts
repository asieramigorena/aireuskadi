import { afterEach, beforeEach, describe, expect, test, vi, type Mock } from "vitest";
import { setLanguage } from "../src/i18n";
import { renderPanel, type PanelView } from "../src/panel";
import type { StationReading, UnitAirQuality, UnitCard, UnitStation } from "../src/types";

const SELECTION = { view: "emissions" as const, pollutant: "NOX", year: 2023 };

const card = (overrides: Partial<UnitCard> = {}): UnitCard => ({
  code: "01036",
  level: "municipality",
  name: "Laudio / Llodio",
  area_km2: 37.3,
  district: { code: "0103", name: "Cantábrica Alavesa" },
  territory: { code: "01", name: "Araba / Álava" },
  emissions: [
    { year: 2023, pollutant: "NOX", name: "Nitrogen oxides", declared_t: 250, t_km2: 6.7, who_ratio: null },
    { year: 2023, pollutant: "CO", name: "Carbon monoxide", declared_t: 0, t_km2: 0, who_ratio: 0.4 },
    { year: 2023, pollutant: "TSP", name: "Particles", declared_t: null, t_km2: null, who_ratio: null },
    { year: 2022, pollutant: "NOX", name: "Nitrogen oxides", declared_t: 99, t_km2: 2.6, who_ratio: null },
  ],
  air_quality: null,
  ...overrides,
});

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

const station = (overrides: Partial<UnitStation> = {}): UnitStation => ({
  id: 7,
  code: "BI1",
  name: "Mazarredo",
  geometry: { type: "Point", coordinates: [-2.93, 43.26] },
  readings: [reading()],
  ...overrides,
});

const air = (overrides: Partial<UnitAirQuality> = {}): UnitAirQuality => ({
  attribution: "Open Data Euskadi, air quality network / Gobierno Vasco, CC BY 4.0",
  measured: true,
  reason: null,
  stations: [station()],
  ...overrides,
});

let root: HTMLElement;
let onClose: Mock<() => void>;

function show(view: PanelView) {
  renderPanel(root, view, SELECTION, onClose);
}

beforeEach(() => {
  root = document.createElement("aside");
  document.body.replaceChildren(root);
  onClose = vi.fn<() => void>();
});

describe("what the panel shows", () => {
  test("closed, it is hidden and has nothing in it", () => {
    show({ status: "closed" });

    expect(root.hidden).toBe(true);
    expect(root.textContent).toBe("");
  });

  test("while the card arrives it says so, and it is open", () => {
    show({ status: "loading" });

    expect(root.hidden).toBe(false);
    expect(root.textContent).toContain("Loading");
    expect(root.getAttribute("aria-busy")).toBe("true");
  });

  test("the card: the name, the kind of unit, where it is and its area", () => {
    show({ status: "card", card: card() });

    expect(root.hidden).toBe(false);
    expect(root.getAttribute("aria-busy")).toBe("false");
    expect(root.querySelector("h2")?.textContent).toBe("Laudio / Llodio");
    const meta = root.querySelector(".meta")?.textContent ?? "";
    expect(meta).toContain("Municipality");
    expect(meta).toContain("Cantábrica Alavesa");
    expect(meta).toContain("Araba / Álava");
    expect(meta).toContain("37.3 km²");
  });

  test("a district or a territory says its own kind, and has no place above it that is not there", () => {
    show({ status: "card", card: card({ level: "territory", district: null, territory: null, name: "Bizkaia" }) });

    expect(root.querySelector(".meta")?.textContent).toBe("Territory · 37.3 km²");
  });

  test("the ratio of the emissions is a cell that may wrap: in Basque it is a long phrase", () => {
    show({ status: "card", card: card() });

    const cells = [...root.querySelectorAll("tbody td.ratio")];
    expect(cells.map((cell) => cell.textContent)).toEqual(["No data", "0.4× the WHO guideline", "No data"]);
  });

  test("the emissions of the selected year, with the label that the API does not give", () => {
    show({ status: "card", card: card() });

    expect(root.querySelector("caption")?.textContent).toBe("Declared industrial emissions in 2023");
    const rows = [...root.querySelectorAll("tbody tr")].map((row) =>
      [...row.querySelectorAll("th, td")].map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ["Nitrogen oxides", "250 t", "6.7 t/km²", "No data"],
      ["Carbon monoxide", "0 t", "0 t/km²", "0.4× the WHO guideline"],
      ["Particles", "No data", "No data", "No data"],
    ]);
  });

  test("the WHO column is only there when some pollutant has a value, so that it is not a column of No data", () => {
    const withoutRatios = card({
      emissions: card().emissions.map((emission) => ({ ...emission, who_ratio: null })),
    });

    show({ status: "card", card: withoutRatios });

    const headers = [...root.querySelectorAll("thead th")].map((cell) => cell.textContent);
    expect(headers).toEqual(["Pollutant", "Declared", "Per km²"]);
    expect(root.querySelector("tbody tr")?.querySelectorAll("th, td")).toHaveLength(3);

    show({ status: "card", card: card() });

    expect([...root.querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual([
      "Pollutant",
      "Declared",
      "Per km²",
      "WHO guideline",
    ]);
  });

  test("the pollutant of the map is marked", () => {
    show({ status: "card", card: card() });

    const marked = [...root.querySelectorAll("tbody tr[aria-current='true']")];
    expect(marked.map((row) => row.querySelector("th")?.textContent)).toEqual(["Nitrogen oxides"]);
  });

  test("a year without emissions says so instead of showing an empty table", () => {
    show({ status: "card", card: card({ emissions: [] }) });

    expect(root.querySelector("table")).toBeNull();
    expect(root.textContent).toContain("No declared emissions in 2023");
  });

  test("an error is said and announced", () => {
    show({ status: "error", message: "Unit 99999 not found." });

    expect(root.hidden).toBe(false);
    expect(root.querySelector("[role='alert']")?.textContent).toBe("Unit 99999 not found.");
  });

  test("showing another view replaces the one before", () => {
    show({ status: "card", card: card() });
    show({ status: "card", card: card({ name: "Other" }) });

    expect(root.querySelectorAll("h2")).toHaveLength(1);
    expect(root.querySelector("h2")?.textContent).toBe("Other");
  });
});

describe("the air quality of the unit", () => {
  const section = () => root.querySelector("section.air-quality");
  const rowsOf = (scope: Element | null) =>
    [...(scope?.querySelectorAll("tbody tr") ?? [])].map((row) =>
      [...row.querySelectorAll("th, td")].map((cell) => cell.textContent),
    );

  test("it comes after the emissions, with its own heading", () => {
    show({ status: "card", card: card({ air_quality: air() }) });

    expect(section()?.querySelector("h3")?.textContent).toBe("Air quality");
    const children = [...root.children].map((child) => child.tagName);
    expect(children.indexOf("TABLE")).toBeLessThan(children.indexOf("SECTION"));
  });

  test("in the map of the air quality it comes first, because it is what the person came to see", () => {
    renderPanel(root, { status: "card", card: card({ air_quality: air() }) }, { ...SELECTION, view: "air", pollutant: "NO2" }, onClose);

    const children = [...root.children].map((child) => child.tagName);
    expect(children.indexOf("SECTION")).toBeLessThan(children.indexOf("TABLE"));
    expect(root.children[1].tagName).toBe("P"); // the place of the unit comes first, under its name
  });

  test("the emissions table is still there in the map of the air quality, and no row of it is marked: the map is not showing it", () => {
    renderPanel(root, { status: "card", card: card({ air_quality: air() }) }, { ...SELECTION, view: "air", pollutant: "CO" }, onClose);

    expect(root.querySelector("caption")?.textContent).toBe("Declared industrial emissions in 2023");
    expect(root.querySelector("tr[aria-current='true']")).toBeNull();
  });

  test("each station is a block with its name, and its readings are a table of the pollutants", () => {
    const two = air({
      stations: [
        station({ readings: [reading(), reading({ pollutant: "PM10", value: 12, who_ratio: 0.27 })] }),
        station({ id: 8, code: "BI2", name: "Kantauri", readings: [reading({ pollutant: "O3", value: 61, who_period: "8h", who_samples: null, who_ratio: 0.61 })] }),
      ],
    });

    show({ status: "card", card: card({ air_quality: two }) });

    const blocks = [...(section()?.querySelectorAll("details") ?? [])];
    expect(blocks.map((block) => block.querySelector("summary")?.textContent)).toEqual(["Mazarredo", "Kantauri"]);
    expect([...blocks[0].querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual([
      "Pollutant",
      "Latest",
      "WHO guideline",
    ]);
    expect(rowsOf(blocks[0])).toEqual([
      ["Nitrogen dioxide", "19 µg/m³", "0.6× the WHO guideline"],
      ["Particles PM10", "12 µg/m³", "0.27× the WHO guideline"],
    ]);
    expect(rowsOf(blocks[1])).toEqual([["Ozone", "61 µg/m³", "0.61× the WHO guideline"]]);
  });

  test("a pollutant that the emissions of the unit name is shown with that name, and the value stays in one line", () => {
    const readings = [reading({ pollutant: "TSP", value: 12 })];
    show({ status: "card", card: card({ air_quality: air({ stations: [station({ readings })] }) }) });

    expect(rowsOf(section())[0][0]).toBe("Particles");
    expect(section()?.querySelector("td .measure")?.textContent).toBe("12 µg/m³");
  });

  describe("the station that the person chose on the map", () => {
    const three = () =>
      air({
        stations: [station({ id: 7, name: "Seven" }), station({ id: 8, name: "Eight" }), station({ id: 9, name: "Nine" })],
      });
    const blocks = () => [...(section()?.querySelectorAll("details") ?? [])];

    test("is open and marked, and the other ones stay closed", () => {
      show({ status: "card", card: card({ air_quality: three() }), station: 8 });

      expect(blocks().map((block) => block.open)).toEqual([false, true, false]);
      expect(blocks().map((block) => block.getAttribute("aria-current"))).toEqual([null, "true", null]);
    });

    test("is brought into view, because the panel is short on a phone and the list can be long", () => {
      const scroll = vi.fn();
      window.HTMLElement.prototype.scrollIntoView = scroll;

      show({ status: "card", card: card({ air_quality: three() }), station: 9 });

      expect(scroll).toHaveBeenCalledTimes(1);
      expect(scroll.mock.contexts[0]).toBe(blocks()[2]);
      expect(scroll).toHaveBeenCalledWith({ block: "start" });
    });

    test("when it is not one of the stations of the unit nothing is opened and nothing breaks", () => {
      const scroll = vi.fn();
      window.HTMLElement.prototype.scrollIntoView = scroll;

      show({ status: "card", card: card({ air_quality: three() }), station: 99999 });

      expect(blocks().map((block) => block.open)).toEqual([false, false, false]);
      expect(section()?.querySelector("[aria-current]")).toBeNull();
      expect(scroll).not.toHaveBeenCalled();
    });

    test("without a station nothing is marked, even when there is only one and it is open", () => {
      show({ status: "card", card: card({ air_quality: air() }) });
      expect(section()?.querySelector("[aria-current]")).toBeNull();
      expect(blocks()[0].open).toBe(true);

      show({ status: "card", card: card({ air_quality: air() }), station: null });
      expect(section()?.querySelector("[aria-current]")).toBeNull();
    });

    test("a station without values that was chosen is open and says so", () => {
      const quiet = air({ measured: false, reason: "no_data", stations: [station({ id: 7, readings: [] }), station({ id: 8, readings: [] })] });

      show({ status: "card", card: card({ air_quality: quiet }), station: 8 });

      expect(blocks().map((block) => block.open)).toEqual([false, true]);
      expect(blocks()[1].textContent).toContain("No values yet.");
    });
  });

  test("a unit with one station shows it open; with several they are closed, so that the list can be read", () => {
    show({ status: "card", card: card({ air_quality: air() }) });
    expect(section()?.querySelector("details")?.open).toBe(true);

    show({ status: "card", card: card({ air_quality: air({ stations: [station(), station({ id: 8, name: "Other" })] }) }) });
    expect([...(section()?.querySelectorAll("details") ?? [])].map((block) => block.open)).toEqual([false, false]);
  });

  test("the hour of the latest value of the station is said, and a value that is older says its own", () => {
    const old = reading({ pollutant: "SO2", value: 3, ts: "2026-11-10T02:00:00.000Z" });
    show({ status: "card", card: card({ air_quality: air({ stations: [station({ readings: [reading(), old] })] }) }) });

    expect(section()?.querySelector(".updated")?.textContent).toBe("Latest value: 11 Nov, 14:00 UTC");
    const cells = [...(section()?.querySelectorAll("tbody tr") ?? [])].map((row) => row.querySelectorAll("td")[0].textContent);
    expect(cells).toEqual(["19 µg/m³", "3 µg/m³ (10 Nov, 02:00 UTC)"]);
  });

  test("the latest value of the station is the newest one, wherever it is in the list", () => {
    const old = reading({ pollutant: "SO2", value: 3, ts: "2026-11-10T02:00:00.000Z" });
    show({ status: "card", card: card({ air_quality: air({ stations: [station({ readings: [old, reading()] })] }) }) });

    expect(section()?.querySelector(".updated")?.textContent).toBe("Latest value: 11 Nov, 14:00 UTC");
    const cells = [...(section()?.querySelectorAll("tbody tr") ?? [])].map((row) => row.querySelectorAll("td")[0].textContent);
    expect(cells).toEqual(["3 µg/m³ (10 Nov, 02:00 UTC)", "19 µg/m³"]);
  });

  test("a day that is not complete is said", () => {
    show({ status: "card", card: card({ air_quality: air({ stations: [station({ readings: [reading({ who_samples: 19 })] })] }) }) });

    expect(rowsOf(section())[0][2]).toBe("0.6× the WHO guideline (19 of 24 hours)");
  });

  test("a pollutant without ratio says why, and no ratio is invented", () => {
    const readings = [
      reading({ pollutant: "NO2", who_ratio: null, who_samples: 10 }),
      reading({ pollutant: "H2S", who_period: null, who_guideline_ugm3: null, who_samples: null, who_ratio: null }),
    ];
    show({ status: "card", card: card({ air_quality: air({ stations: [station({ readings })] }) }) });

    expect(rowsOf(section()).map((row) => row[2])).toEqual(["Not enough data", "No WHO guideline"]);
  });

  test("a station without values is in the list and says so", () => {
    show({ status: "card", card: card({ air_quality: air({ stations: [station({ readings: [] }), station({ id: 8, name: "Other" })] }) }) });

    const first = section()?.querySelector("details");
    expect(first?.textContent).toContain("No values yet.");
    expect(first?.querySelector("table")).toBeNull();
  });

  test("the source is credited", () => {
    show({ status: "card", card: card({ air_quality: air() }) });

    expect(section()?.querySelector(".source")?.textContent).toBe(
      "Open Data Euskadi, air quality network / Gobierno Vasco, CC BY 4.0",
    );
  });

  test.each([
    ["no_station", "There is no air quality station in this municipality."],
    ["no_data", "The stations of this municipality have no values yet."],
    ["level_not_supported", "Stations are shown for municipalities: choose one to see its air quality."],
  ] as const)("without a measurement the reason %s is said in words, and there is no table", (reason, text) => {
    const stations = reason === "level_not_supported" ? null : [];
    show({ status: "card", card: card({ air_quality: air({ measured: false, reason, stations }) }) });

    expect(section()?.querySelector("p.none")?.textContent).toBe(text);
    expect(section()?.querySelector("table")).toBeNull();
    expect(section()?.querySelector(".source")).toBeNull();
  });

  test.each(["something_new", "toString", "constructor"])(
    "a reason that the panel does not know (%s) is not shown as a code: it says that there is nothing to show",
    (code) => {
      const strange = air({ measured: false, reason: code as never, stations: [] });

      show({ status: "card", card: card({ air_quality: strange }) });

      expect(section()?.querySelector("p.none")?.textContent).toBe("There is no air quality to show for this unit.");
    },
  );

  test("a municipality whose stations have no values lists them with the reason", () => {
    const quiet = air({ measured: false, reason: "no_data", stations: [station({ readings: [] })] });

    show({ status: "card", card: card({ air_quality: quiet }) });

    expect(section()?.querySelector("p.none")?.textContent).toBe("The stations of this municipality have no values yet.");
    expect(section()?.querySelector("summary")?.textContent).toBe("Mazarredo");
  });

  test("when the service gave nothing the card still shows and says that the air quality is not available", () => {
    show({ status: "card", card: card({ air_quality: null }) });

    expect(root.querySelector("h2")?.textContent).toBe("Laudio / Llodio");
    expect(section()?.querySelector("p.none")?.textContent).toBe("Air quality is not available right now.");
  });
});

describe("the air quality can never break the card", () => {
  // The gateway sends typed data, but this is the part that comes from another service: whatever it
  // sends, the name of the unit and the emissions are still shown.
  const BROKEN: [string, unknown][] = [
    ["stations that are not a list", { stations: "x" }],
    ["readings that are not a list", { stations: [{ ...station(), readings: null }] }],
    ["a time that is not a time", { stations: [{ ...station(), readings: [reading({ ts: "garbage" })] }] }],
    ["a value that is not a number", { stations: [{ ...station(), readings: [reading({ value: null as never })] }] }],
    ["a unit that is not text", { stations: [{ ...station(), readings: [reading({ unit: null as never })] }] }],
    ["a reading that is nothing", { stations: [{ ...station(), readings: [null] }] }],
  ];

  test.each(BROKEN)("with %s the card is shown and the section says that it is not available", (_name, bad) => {
    show({ status: "card", card: card({ air_quality: { ...air(), ...(bad as object) } }) });

    expect(root.querySelector("h2")?.textContent).toBe("Laudio / Llodio");
    expect(root.querySelector("table caption")?.textContent).toBe("Declared industrial emissions in 2023");
    const section = root.querySelector("section.air-quality");
    expect(section?.querySelector("p.none")?.textContent).toBe("Air quality is not available right now.");
    expect(section?.querySelector("details")).toBeNull();
    expect(root.querySelectorAll("section.air-quality")).toHaveLength(1);
  });
});

describe("what comes from the API is text, never HTML", () => {
  const HOSTILE = '<img src=x onerror="window.__owned = 1"><script>window.__owned = 2</script>';

  test("in the name, the places and the pollutants", () => {
    show({
      status: "card",
      card: card({
        name: HOSTILE,
        district: { code: "0103", name: HOSTILE },
        territory: { code: "01", name: HOSTILE },
        emissions: [
          { year: 2023, pollutant: "NOX", name: HOSTILE, declared_t: 1, t_km2: 1, who_ratio: null },
        ],
      }),
    });

    expect(root.querySelector("img, script")).toBeNull();
    expect(root.querySelector("h2")?.textContent).toBe(HOSTILE);
    expect((window as unknown as { __owned?: number }).__owned).toBeUndefined();
  });

  test("in the stations, their pollutants and the source", () => {
    const hostile = air({
      attribution: HOSTILE,
      stations: [station({ name: HOSTILE, readings: [reading({ pollutant: HOSTILE, unit: HOSTILE })] })],
    });

    show({ status: "card", card: card({ air_quality: hostile }) });

    expect(root.querySelector("img, script")).toBeNull();
    expect(root.querySelector("summary")?.textContent).toBe(HOSTILE);
    expect(root.querySelector("table.readings tbody th")?.textContent).toBe(HOSTILE);
    expect(root.querySelector(".measure")?.textContent).toContain(HOSTILE);
    expect(root.querySelector(".source")?.textContent).toBe(HOSTILE);
    expect((window as unknown as { __owned?: number }).__owned).toBeUndefined();
  });

  test("in an error", () => {
    show({ status: "error", message: HOSTILE });

    expect(root.querySelector("img, script")).toBeNull();
    expect(root.querySelector("[role='alert']")?.textContent).toBe(HOSTILE);
  });
});

describe("closing", () => {
  test("the button has a name for whoever cannot see it, and asks to close", () => {
    show({ status: "card", card: card() });

    const button = root.querySelector("button");
    expect(button?.getAttribute("aria-label")).toBe("Close the panel");
    button?.click();

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("an error can be closed too", () => {
    show({ status: "error", message: "x" });

    root.querySelector("button")?.click();

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

// --- the language of the panel --------------------------------------------------------------------

afterEach(() => setLanguage("en"));

describe("the panel in Spanish", () => {
  const stations = () =>
    air({ stations: [station({ readings: [reading({ pollutant: "NO2" }), reading({ pollutant: "H2S", who_samples: 19 })] })] });

  test("the card: the kind of unit, the emissions and the air quality, with their columns", () => {
    setLanguage("es");
    show({ status: "card", card: card({ air_quality: stations() }) });

    expect(root.querySelector(".meta")?.textContent).toBe("Municipio · Cantábrica Alavesa · Araba / Álava · 37,3 km²");
    expect(root.querySelector("caption")?.textContent).toBe("Emisiones industriales declaradas en 2023");
    expect([...root.querySelectorAll("table")[0].querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual([
      "Contaminante",
      "Declarado",
      "Por km²",
      "Valor guía OMS",
    ]);
    expect(root.querySelector("h3")?.textContent).toBe("Calidad del aire");
    expect(root.querySelector("section.air-quality thead")?.textContent).toBe("ContaminanteÚltimoValor guía OMS");
    expect(root.querySelector("button")?.getAttribute("aria-label")).toBe("Cerrar el panel");
  });

  test("the names of the pollutants of the emissions are Spanish, by their code", () => {
    setLanguage("es");
    show({ status: "card", card: card() });

    const names = [...root.querySelectorAll("tbody th")].map((cell) => cell.textContent);
    expect(names).toEqual(["Óxidos de nitrógeno (NOx)", "Monóxido de carbono", "Partículas en suspensión totales"]);
  });

  test("the stations: the hour, the names, the numbers and the partial day", () => {
    setLanguage("es");
    show({ status: "card", card: card({ air_quality: stations() }) });

    expect(root.querySelector(".updated")?.textContent).toBe("Último valor: 11 nov, 14:00 UTC");
    expect(
      [...root.querySelectorAll("section.air-quality tbody tr")].map((row) => [...row.querySelectorAll("th, td")].map((cell) => cell.textContent)),
    ).toEqual([
      ["Dióxido de nitrógeno", "19 µg/m³", "0,6× el valor guía de la OMS"],
      ["H2S", "19 µg/m³", "0,6× el valor guía de la OMS (19 de 24 horas)"],
    ]);
  });

  test("a pollutant of a station that the language names only for the emissions takes that name too, in Spanish and in Basque", () => {
    const benzene = { year: 2023, pollutant: "BENZENE", name: "Benzene", declared_t: 1, t_km2: 1, who_ratio: null };
    const withBenzene = () =>
      card({
        emissions: [...card().emissions, benzene],
        air_quality: air({ stations: [station({ readings: [reading({ pollutant: "BENZENE", who_period: null, who_ratio: null })] })] }),
      });
    const nameInStation = () => root.querySelector("section.air-quality tbody th")?.textContent;

    show({ status: "card", card: withBenzene() });
    expect(nameInStation()).toBe("Benzene");

    setLanguage("es");
    show({ status: "card", card: withBenzene() });
    expect(nameInStation()).toBe("Benceno");

    setLanguage("eu");
    show({ status: "card", card: withBenzene() });
    expect(nameInStation()).toBe("Bentzenoa");
  });

  test("nothing to show, in words", () => {
    setLanguage("es");

    show({ status: "card", card: card({ air_quality: null }) });
    expect(root.querySelector("p.none")?.textContent).toBe("La calidad del aire no está disponible en este momento.");

    show({ status: "card", card: card({ air_quality: air({ measured: false, reason: "no_station", stations: [] }) }) });
    expect(root.querySelector("p.none")?.textContent).toBe("No hay ninguna estación de calidad del aire en este municipio.");

    show({ status: "card", card: card({ emissions: [] }) });
    expect(root.textContent).toContain("Sin emisiones declaradas en 2023.");
  });

  test("loading and an error", () => {
    setLanguage("es");

    show({ status: "loading" });
    expect(root.textContent).toContain("Cargando…");

    show({ status: "error", message: "x" });
    expect(root.querySelector("h2")?.textContent).toBe("Algo ha salido mal");
  });
});

describe("the panel in Basque", () => {
  test("the card, with the names and the columns in Basque", () => {
    setLanguage("eu");
    show({ status: "card", card: card({ air_quality: air() }) });

    expect(root.querySelector(".meta")?.textContent).toBe("Udalerria · Cantábrica Alavesa · Araba / Álava · 37,3 km²");
    expect(root.querySelector("caption")?.textContent).toBe("Aitortutako isuri industrialak, 2023");
    expect([...root.querySelectorAll("tbody th")].slice(0, 3).map((cell) => cell.textContent)).toEqual([
      "Nitrogeno oxidoak (NOx)",
      "Karbono monoxidoa",
      "Airean esekitako partikula guztiak",
    ]);
    expect(root.querySelector("h3")?.textContent).toBe("Aire kalitatea");
    expect(root.querySelector(".updated")?.textContent).toBe("Azken balioa: aza. 11, 14:00 UTC");
    expect(root.querySelector("button")?.getAttribute("aria-label")).toBe("Itxi panela");
  });

  test("nothing to show, in words", () => {
    setLanguage("eu");

    show({ status: "card", card: card({ air_quality: air({ measured: false, reason: "level_not_supported", stations: null }) }) });
    expect(root.querySelector("p.none")?.textContent).toBe(
      "Estazioak udalerrietan erakusten dira: aukeratu bat haren aire kalitatea ikusteko.",
    );

    show({ status: "card", card: card({ air_quality: air({ measured: false, reason: "something_new" as never, stations: [] }) }) });
    expect(root.querySelector("p.none")?.textContent).toBe("Ez dago erakusteko aire kalitaterik unitate honetarako.");
  });

  test("a panel that is drawn again in another language has nothing left of the first one", () => {
    setLanguage("es");
    show({ status: "card", card: card({ air_quality: air() }) });
    setLanguage("eu");
    show({ status: "card", card: card({ air_quality: air() }) });

    expect(root.textContent).not.toContain("Calidad del aire");
    expect(root.textContent).not.toContain("Municipio");
    expect(root.querySelectorAll("h3")).toHaveLength(1);
  });
});
