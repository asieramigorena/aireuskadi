import { beforeEach, describe, expect, test, vi, type Mock } from "vitest";
import { renderPanel, type PanelView } from "../src/panel";
import type { UnitCard } from "../src/types";

const SELECTION = { pollutant: "NOX", year: 2023 };

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
