import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { setLanguage } from "../src/i18n";
import { renderPanel } from "../src/panel";
import { ApiError } from "../src/api";
import { focusedTrendControl, loadTrend, restoreTrendFocus, trendSeries } from "../src/trend";
import type { Inventory } from "../src/types";

const SELECTION = { view: "emissions" as const, pollutant: "NOX", year: 2023 };

const inventory = (overrides: Partial<Inventory> = {}): Inventory => ({
  attribution: "Eusko Jaurlaritza / Gobierno Vasco (Open Data Euskadi, CC BY 4.0)",
  pollutant: "NOX",
  unit: "t",
  classification: "SNAP",
  series: [
    { sector: { code: "01", name: "Combustión en la producción" }, year: 1990, value: 100 },
    { sector: { code: "01", name: "Combustión en la producción" }, year: 1991, value: 80 },
    { sector: { code: "07", name: "Transporte por carretera" }, year: 1991, value: 20 },
  ],
  ...overrides,
});

let root: HTMLElement;
let navigate: ReturnType<typeof vi.fn<(url: string) => void>>;

beforeEach(() => {
  root = document.createElement("aside");
  document.body.replaceChildren(root);
  navigate = vi.fn<(url: string) => void>();
});

afterEach(() => setLanguage("en"));

const show = (data: Inventory | null, classification: "SNAP" | "NFR" = "SNAP", pollutant = "NOX") =>
  renderPanel(root, { status: "trend", inventory: data, classification }, { ...SELECTION, pollutant }, () => {}, navigate);

describe("the series of the chart", () => {
  test("has every year once and one line per sector, with 0 in a year that the sector does not have", () => {
    setLanguage("es"); // the names of the source, which are in Spanish
    expect(trendSeries(inventory())).toEqual({
      years: [1990, 1991],
      sectors: [
        { code: "01", name: "Combustión en la producción", values: [100, 80] },
        { code: "07", name: "Transporte por carretera", values: [0, 20] },
      ],
    });
  });

  test("the sectors are named in the language of the page, and keep the name of the source otherwise", () => {
    setLanguage("en");
    expect(trendSeries(inventory()).sectors.map((sector) => sector.name)).toEqual([
      "Combustion in energy and transformation industries",
      "Road transport",
    ]);

    setLanguage("es");
    expect(trendSeries(inventory()).sectors[0].name).toBe("Combustión en la producción");
  });
});

describe("the trend in the panel", () => {
  test("says what it shows, from the first year to the last, with the total of each", () => {
    show(inventory());

    expect(root.querySelector("h2")?.textContent).toContain("Nitrogen oxides");
    expect(root.querySelector("canvas")?.getAttribute("aria-label")).toBe("From 100 t in 1990 to 100 t in 1991.");
    expect(root.textContent).toContain("CC BY 4.0");
  });

  test("the pollutant can be chosen among the ones of the inventory, and choosing one navigates to its trend", () => {
    show(inventory());

    const choice = root.querySelector("select") as HTMLSelectElement;
    expect([...choice.options].map((option) => option.value)).toEqual(["NOX", "SOX", "NH3", "NMVOC", "CO", "TSP", "PM10", "PM25", "CH4"]);
    expect(choice.value).toBe("NOX");
    choice.value = "SOX";
    choice.dispatchEvent(new Event("change"));
    expect(navigate).toHaveBeenLastCalledWith("/trend?pollutant=SOX");
  });

  test("the SNAP and NFR sectors are two links, and the one that is shown is marked", () => {
    show(inventory(), "NFR");

    const links = [...root.querySelectorAll("a.sectors")];
    expect(links.map((link) => [link.textContent, link.getAttribute("href"), link.getAttribute("aria-current")])).toEqual([
      ["SNAP", "/trend", null],
      ["NFR", "/trend?sectors=nfr", "true"],
    ]);
  });

  test("methane has no sectors: there is no choice of them, and it says so", () => {
    show(inventory({ pollutant: "CH4", classification: "TOTAL" }), "SNAP", "CH4");

    expect(root.querySelectorAll("a.sectors")).toHaveLength(0);
    expect(root.textContent).toContain("Methane is published only as a total.");
  });

  test("the NFR sectors of the particles in 2024 do not add up to the published total, and it is said", () => {
    show(inventory({ pollutant: "TSP", classification: "NFR" }), "NFR", "TSP");

    expect(root.textContent).toContain("In 2024 the NFR sectors of the total suspended particles do not add up to the published total.");
  });

  test("a pollutant that the inventory does not have says so, and the list lets choose another", () => {
    show(null, "SNAP", "CO2");

    expect(root.textContent).toContain("The inventory has no data of this pollutant.");
    expect(root.querySelector("canvas")).toBeNull();
    expect(root.querySelector("select")).not.toBeNull();
  });
});

describe("the words of the chart", () => {
  test("a table that is not seen says the tonnes of each sector in the last year", () => {
    show(inventory());

    // Inside a box that is not seen: the box hides all of it, the caption too (a hidden table alone
    // still showed its caption in some browsers, over the rest of the panel).
    const table = root.querySelector(".visually-hidden > table");
    expect(table?.querySelector("caption")?.textContent).toBe("Tonnes by sector in 1991");
    expect([...(table?.querySelectorAll("tbody tr") ?? [])].map((row) => row.textContent)).toEqual([
      "Combustion in energy and transformation industries80 t",
      "Road transport20 t",
    ]);
  });
});

describe("the keyboard in the trend", () => {
  test("the control that had the focus has it again after the panel is drawn again", () => {
    show(inventory());
    (root.querySelector("select") as HTMLSelectElement).focus();
    const which = focusedTrendControl(root);

    show(inventory());
    restoreTrendFocus(root, which);

    expect(document.activeElement).toBe(root.querySelector("select"));
  });

  test("after choosing the sectors, the focus is on the ones that are shown now", () => {
    show(inventory(), "SNAP");
    (root.querySelector("a.sectors") as HTMLAnchorElement).focus();
    const which = focusedTrendControl(root);

    show(inventory(), "NFR");
    restoreTrendFocus(root, which);

    expect(document.activeElement).toBe(root.querySelector("a.sectors[aria-current='true']"));
  });
});

describe("asking the inventory", () => {
  test("methane is asked as a total, and the other pollutants by the sectors that are chosen", async () => {
    const inventoryOf = vi.fn(async () => inventory());

    await loadTrend({ inventory: inventoryOf }, "CH4", "NFR");
    await loadTrend({ inventory: inventoryOf }, "SOX", "NFR");

    expect(inventoryOf.mock.calls.map((call) => call.slice(0, 2))).toEqual([["CH4", "TOTAL"], ["SOX", "NFR"]]);
  });

  test("a pollutant that the inventory does not have (404) is no data, and any other failure is a failure", async () => {
    await expect(loadTrend({ inventory: async () => { throw new ApiError(404); } }, "CO2", "SNAP")).resolves.toBeNull();
    await expect(loadTrend({ inventory: async () => { throw new ApiError(503); } }, "NOX", "SNAP")).rejects.toThrow(ApiError);
  });
});
