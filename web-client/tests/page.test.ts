import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { setLanguage } from "../src/i18n";
import { applyPageTexts } from "../src/page";

// The parts of index.html that have a text that is not drawn by anything else.
function mount() {
  document.documentElement.lang = "en";
  document.body.innerHTML = `
    <div id="map" role="img" aria-label=""></div>
    <nav id="controls" aria-label=""></nav>
    <nav id="languages" aria-label=""></nav>
    <aside id="panel" aria-label="" hidden></aside>
    <p id="emissions-credit"></p>
    <p id="air-credit"></p>`;
}

const label = (id: string) => document.getElementById(id)?.getAttribute("aria-label");
const text = (id: string) => document.getElementById(id)?.textContent;

beforeEach(mount);
afterEach(() => setLanguage("en"));

describe("the texts of the page that nothing else draws", () => {
  test("in English: the labels, the credit of the emissions and the language of the page", () => {
    applyPageTexts("emissions", null);

    expect(document.documentElement.lang).toBe("en");
    expect(label("controls")).toBe("Choose the map");
    expect(label("languages")).toBe("Language");
    expect(label("panel")).toBe("Details of the unit");
    expect(label("map")).toBe("3D map of the declared industrial emissions of the Basque Country");
    expect(text("emissions-credit")).toBe("Emissions: E-PRTR register, Open Data Euskadi, CC BY 4.0.");
  });

  test("in Spanish", () => {
    setLanguage("es");
    applyPageTexts("emissions", null);

    expect(document.documentElement.lang).toBe("es");
    expect(label("controls")).toBe("Elige el mapa");
    expect(label("languages")).toBe("Idioma");
    expect(label("panel")).toBe("Detalles de la unidad");
    expect(text("emissions-credit")).toBe("Emisiones: registro E-PRTR, Open Data Euskadi, CC BY 4.0.");
  });

  test("in Basque", () => {
    setLanguage("eu");
    applyPageTexts("emissions", null);

    expect(document.documentElement.lang).toBe("eu");
    expect(label("controls")).toBe("Aukeratu mapa");
    expect(label("languages")).toBe("Hizkuntza");
    expect(label("panel")).toBe("Unitatearen xehetasunak");
    expect(text("emissions-credit")).toBe("Isuriak: E-PRTR erregistroa, Open Data Euskadi, CC BY 4.0.");
  });

  test("the label of the map says which map it is, in the language", () => {
    setLanguage("es");
    applyPageTexts("air", "x");
    expect(label("map")).toBe("Mapa 3D de la calidad del aire más reciente medida en las estaciones de Euskadi");

    setLanguage("eu");
    applyPageTexts("emissions", null);
    expect(label("map")).toBe("Euskadiko isuri industrial aitortuen 3D mapa");
  });
});

describe("the credits of what the map shows", () => {
  test("the emissions: their credit is shown, and the one of the air quality is empty", () => {
    applyPageTexts("emissions", "Credit of the stations");

    expect((document.getElementById("emissions-credit") as HTMLElement).hidden).toBe(false);
    expect(text("air-credit")).toBe("");
  });

  test("the air quality: the credit of the emissions is hidden and the one of the stations is said, in the language", () => {
    applyPageTexts("air", "Open Data Euskadi, CC BY 4.0");
    expect((document.getElementById("emissions-credit") as HTMLElement).hidden).toBe(true);
    expect(text("air-credit")).toBe("Air quality: Open Data Euskadi, CC BY 4.0");

    setLanguage("es");
    applyPageTexts("air", "Open Data Euskadi, CC BY 4.0");
    expect(text("air-credit")).toBe("Calidad del aire: Open Data Euskadi, CC BY 4.0");

    setLanguage("eu");
    applyPageTexts("air", "Open Data Euskadi, CC BY 4.0");
    expect(text("air-credit")).toBe("Aire kalitatea: Open Data Euskadi, CC BY 4.0");
  });

  test("the air quality without its stations yet (loading, or an error) says no credit", () => {
    applyPageTexts("air", null);

    expect(text("air-credit")).toBe("");
  });

  test("the text of the credit is text, never HTML", () => {
    applyPageTexts("air", '<img src=x onerror="window.__page = 1">');

    expect(document.getElementById("air-credit")?.querySelector("img")).toBeNull();
    expect((window as unknown as { __page?: number }).__page).toBeUndefined();
  });
});

describe("a page that is missing one of the parts", () => {
  test("does not break: what is there is written, and what is not is left", () => {
    document.body.innerHTML = '<nav id="controls" aria-label=""></nav>';
    setLanguage("es");

    expect(() => applyPageTexts("emissions", null)).not.toThrow();
    expect(label("controls")).toBe("Elige el mapa");
  });
});
