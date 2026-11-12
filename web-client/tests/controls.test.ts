import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { renderControls, renderLanguages } from "../src/controls";
import { setLanguage } from "../src/i18n";
import type { Selection } from "../src/router";

const emissions: Selection = { view: "emissions", pollutant: "NOX", year: 2023 };
const air = (pollutant = "NO2"): Selection => ({ view: "air", pollutant, year: 2023 });

let root: HTMLElement;
let navigate: ReturnType<typeof vi.fn<(url: string) => void>>;

beforeEach(() => {
  root = document.createElement("nav");
  document.body.replaceChildren(root);
  navigate = vi.fn<(url: string) => void>();
});

const show = (selection: Selection, unit: string | null = null, station: number | null = null) =>
  renderControls(root, selection, unit, navigate, station);
const links = () => [...root.querySelectorAll("a")];
const select = () => root.querySelector("select");

describe("the switch between the two maps", () => {
  test("are two links with the name of each map, and the one that is shown is marked", () => {
    show(emissions);

    expect(links().map((link) => link.textContent)).toEqual(["Emissions", "Air quality"]);
    expect(links().map((link) => link.getAttribute("aria-current"))).toEqual(["true", null]);

    show(air());

    expect(links().map((link) => link.getAttribute("aria-current"))).toEqual([null, "true"]);
  });

  test("are links with an address, so that they can be opened in another tab and Back works", () => {
    show(emissions);

    expect(links().map((link) => link.getAttribute("href"))).toEqual(["/", "/?view=air"]);
  });

  test("the other map starts with its own pollutant, and the one that is shown keeps its own", () => {
    show({ view: "emissions", pollutant: "CO", year: 2019 });
    expect(links().map((link) => link.getAttribute("href"))).toEqual(["/?pollutant=CO&year=2019", "/?view=air"]);

    show(air("PM10"));
    expect(links().map((link) => link.getAttribute("href"))).toEqual(["/", "/?view=air&pollutant=PM10"]);
  });

  test("with a unit open the switch keeps it: only the map changes", () => {
    show(emissions, "48020");
    expect(links().map((link) => link.getAttribute("href"))).toEqual(["/unit/48020", "/unit/48020?view=air"]);

    show(air("O3"), "48020");
    expect(links().map((link) => link.getAttribute("href"))).toEqual(["/unit/48020", "/unit/48020?view=air&pollutant=O3"]);
  });

  test("with a station open the air quality keeps it, and the map of the emissions, which has none, does not", () => {
    show(air("O3"), "48020", 212);

    expect(links().map((link) => link.getAttribute("href"))).toEqual([
      "/unit/48020",
      "/unit/48020?view=air&pollutant=O3&station=212",
    ]);
  });

  test("a click is a navigation of the page and not of the browser", () => {
    show(emissions);
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });

    links()[1].dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
    expect(navigate).toHaveBeenCalledWith("/?view=air");
  });

  test.each([
    ["control", { ctrlKey: true }],
    ["meta", { metaKey: true }],
    ["shift", { shiftKey: true }],
    ["alt", { altKey: true }],
    ["the middle button", { button: 1 }],
  ])("a click with %s is left to the browser, which opens another tab", (_name, init) => {
    show(emissions);
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, ...init });

    links()[1].dispatchEvent(click);

    expect(click.defaultPrevented).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe("the selector of the pollutant of the air quality", () => {
  test("is only there in the map of the air quality, because the emissions have their own pollutants", () => {
    show(emissions);
    expect(select()).toBeNull();

    show(air());
    expect(select()).not.toBeNull();
  });

  test("has the name of the pollutants that have a guideline, and the one of the map is the selected one", () => {
    show(air("PM10"));

    const options = [...root.querySelectorAll("option")];
    expect(options.map((option) => option.textContent)).toEqual([
      "Nitrogen dioxide",
      "Particles PM2.5",
      "Particles PM10",
      "Ozone",
      "Sulphur dioxide",
      "Carbon monoxide",
    ]);
    expect(options.map((option) => option.value)).toEqual(["NO2", "PM25", "PM10", "O3", "SO2", "CO"]);
    expect(select()?.value).toBe("PM10");
  });

  test("a pollutant that is not in the list (the address says it) is still the one that is shown, and does not lie", () => {
    show(air("NOX"));

    expect(select()?.value).toBe("NOX");
    expect([...root.querySelectorAll("option")].map((option) => option.value)).toEqual([
      "NO2", "PM25", "PM10", "O3", "SO2", "CO", "NOX",
    ]);
  });

  test("has a name for whoever cannot see it", () => {
    show(air());

    expect(select()?.getAttribute("aria-label")).toBe("Pollutant of the air quality");
  });

  test("choosing another one navigates to its map, and keeps the unit that is open", () => {
    show(air());
    (select() as HTMLSelectElement).value = "O3";
    select()?.dispatchEvent(new Event("change", { bubbles: true }));
    expect(navigate).toHaveBeenLastCalledWith("/?view=air&pollutant=O3");

    show(air(), "48020");
    (select() as HTMLSelectElement).value = "CO";
    select()?.dispatchEvent(new Event("change", { bubbles: true }));
    expect(navigate).toHaveBeenLastCalledWith("/unit/48020?view=air&pollutant=CO");
  });

  test("choosing another pollutant keeps the unit and the station that are open", () => {
    show(air(), "48020", 212);
    (select() as HTMLSelectElement).value = "CO";
    select()?.dispatchEvent(new Event("change", { bubbles: true }));

    expect(navigate).toHaveBeenLastCalledWith("/unit/48020?view=air&pollutant=CO&station=212");
  });

  test("choosing the default pollutant gives the address without it", () => {
    show(air("O3"));
    (select() as HTMLSelectElement).value = "NO2";
    select()?.dispatchEvent(new Event("change", { bubbles: true }));

    expect(navigate).toHaveBeenLastCalledWith("/?view=air");
  });
});

describe("the focus of the keyboard", () => {
  test("stays on the control that had it when they are drawn again: choosing with the keyboard does not send the person to the top of the page", () => {
    show(air());
    (select() as HTMLElement).focus();
    expect(document.activeElement).toBe(select());

    show(air("O3"));
    expect(document.activeElement).toBe(select());

    links()[1].focus();
    show(air("O3"));
    expect(document.activeElement).toBe(links()[1]);
  });

  test("a focus that was somewhere else is not taken", () => {
    const other = document.createElement("button");
    document.body.append(other);
    other.focus();

    show(air());

    expect(document.activeElement).toBe(other);
  });

  test("when the control that had it goes away (the selector, back to the emissions), it goes to the last one that is left", () => {
    show(air());
    (select() as HTMLElement).focus();

    show(emissions);

    expect(document.activeElement).toBe(links()[1]);
  });
});

describe("drawing it again", () => {
  test("replaces what was there, and nothing is left of the selector when the map has none", () => {
    show(air());
    show(air("O3"));
    expect(root.querySelectorAll("a")).toHaveLength(2);
    expect(root.querySelectorAll("select")).toHaveLength(1);

    show(emissions);
    expect(root.querySelectorAll("a")).toHaveLength(2);
    expect(root.querySelectorAll("select")).toHaveLength(0);
  });

  test("a pollutant that comes in is text, never HTML", () => {
    show(air('<img src=x onerror="window.__controls = 1">'));

    expect(root.querySelector("img")).toBeNull();
    expect((window as unknown as { __controls?: number }).__controls).toBeUndefined();
  });
});

afterEach(() => setLanguage("en"));

describe("the controls of the maps in Spanish and in Basque", () => {
  test("the names of the two maps, and of the pollutants and of the selector", () => {
    setLanguage("es");
    show(air("O3"));

    expect(links().map((link) => link.textContent)).toEqual(["Emisiones", "Calidad del aire"]);
    expect([...root.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "Dióxido de nitrógeno",
      "Partículas PM2,5",
      "Partículas PM10",
      "Ozono",
      "Dióxido de azufre",
      "Monóxido de carbono",
    ]);
    expect(select()?.getAttribute("aria-label")).toBe("Contaminante de la calidad del aire");

    setLanguage("eu");
    show(air("O3"));
    expect(links().map((link) => link.textContent)).toEqual(["Isuriak", "Aire kalitatea"]);
    expect(select()?.getAttribute("aria-label")).toBe("Aire kalitatearen kutsatzailea");
    expect(root.querySelector("option")?.textContent).toBe("Nitrogeno dioxidoa");
  });

  test("the language that was chosen goes in the address of each map", () => {
    show({ ...emissions, lang: "es" });

    expect(links().map((link) => link.getAttribute("href"))).toEqual(["/?lang=es", "/?view=air&lang=es"]);
  });

  test("and the pollutant that is chosen keeps it", () => {
    show({ ...air(), lang: "eu" });
    (select() as HTMLSelectElement).value = "O3";
    select()?.dispatchEvent(new Event("change", { bubbles: true }));

    expect(navigate).toHaveBeenLastCalledWith("/?view=air&pollutant=O3&lang=eu");
  });
});

describe("the selector of the language", () => {
  const languages = () => [...root.querySelectorAll("a")];
  const draw = (current: "eu" | "es" | "en", selection: Selection = emissions, unit: string | null = null, station: number | null = null) =>
    renderLanguages(root, current, selection, unit, navigate, station);

  test("are three links, with the code of the language as their text and its name as their title", () => {
    draw("eu");

    expect(languages().map((link) => link.textContent)).toEqual(["EU", "ES", "EN"]);
    expect(languages().map((link) => link.getAttribute("title"))).toEqual(["Euskara", "Español", "English"]);
    expect(languages().map((link) => link.getAttribute("lang"))).toEqual(["eu", "es", "en"]);
  });

  test("each is named by the name of its language, not by two letters that a reader would spell out", () => {
    draw("eu");

    expect(languages().map((link) => link.getAttribute("aria-label"))).toEqual(["Euskara", "Español", "English"]);
  });

  test("the one in use is marked", () => {
    draw("es");

    expect(languages().map((link) => link.getAttribute("aria-current"))).toEqual([null, "true", null]);
  });

  test("each is an address, which keeps the map and the pollutant, and says the language", () => {
    draw("eu", air("O3"));

    expect(languages().map((link) => link.getAttribute("href"))).toEqual([
      "/?view=air&pollutant=O3&lang=eu",
      "/?view=air&pollutant=O3&lang=es",
      "/?view=air&pollutant=O3&lang=en",
    ]);
  });

  test("with a unit and a station open, they stay open", () => {
    draw("eu", air(), "48020", 195);

    expect(languages().map((link) => link.getAttribute("href"))).toEqual([
      "/unit/48020?view=air&lang=eu&station=195",
      "/unit/48020?view=air&lang=es&station=195",
      "/unit/48020?view=air&lang=en&station=195",
    ]);
  });

  test("a click is a navigation of the page, and a click with a key is the browser's", () => {
    draw("eu");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
    languages()[1].dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
    expect(navigate).toHaveBeenCalledWith("/?lang=es");

    navigate.mockClear();
    const other = new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true });
    languages()[2].dispatchEvent(other);
    expect(other.defaultPrevented).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  test("the focus stays on the language that had it when they are drawn again", () => {
    draw("eu");
    languages()[1].focus();

    draw("es");

    expect(document.activeElement).toBe(languages()[1]);
  });

  test("drawing them again replaces them", () => {
    draw("eu");
    draw("es");

    expect(root.querySelectorAll("a")).toHaveLength(3);
  });
});
