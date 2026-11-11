import { beforeEach, describe, expect, test } from "vitest";
import { renderLegend } from "../src/legend";
import { legendGradient, ratioLegendGradient } from "../src/scale";

let root: HTMLElement;

beforeEach(() => {
  root = document.createElement("section");
  document.body.replaceChildren(root);
});

const texts = (selector: string) => [...root.querySelectorAll(selector)].map((node) => node.textContent);

describe("the legend of the map of emissions", () => {
  test("says what the colours are, the scale from 0 to the biggest density, and what grey is", () => {
    renderLegend(root, "emissions", "57 t/km²");

    expect(root.getAttribute("aria-label")).toBe("Colour of the units");
    expect(root.querySelector("p")?.textContent).toBe("Declared per km² of each unit");
    expect(texts(".legend-ends span")).toEqual(["0", "57 t/km²"]);
    expect(root.querySelector(".legend-ends.three")).toBeNull();
    expect(root.querySelector(".no-data")?.textContent).toBe("No data");
  });

  test("the bar is the gradient of the colours of the units", () => {
    renderLegend(root, "emissions", "1 t/km²");

    expect((root.querySelector("#legend-bar") as HTMLElement).style.background).toContain("linear-gradient");
    expect((root.querySelector("#legend-bar") as HTMLElement).style.background).toBe(
      ((): string => {
        const probe = document.createElement("div");
        probe.style.background = legendGradient();
        return probe.style.background;
      })(),
    );
  });
});

describe("the legend of the map of the air quality", () => {
  test("says that the colours are the latest value against the guideline, with the guideline marked in the middle", () => {
    renderLegend(root, "air", "ignored");

    expect(root.getAttribute("aria-label")).toBe("Colour of the stations");
    expect(root.querySelector("p")?.textContent).toBe("Latest value vs WHO guideline");
    expect(texts(".legend-ends span")).toEqual(["0", "1× guideline", "2× or more"]);
    expect(root.querySelector(".legend-tick")).not.toBeNull();
    // The class that the stylesheet uses to keep the middle label in the middle.
    expect(root.querySelector(".legend-ends.three")).not.toBeNull();
  });

  test("the bar is the gradient of the ratios, and grey is a station that has no ratio", () => {
    renderLegend(root, "air", "ignored");

    const probe = document.createElement("div");
    probe.style.background = ratioLegendGradient();
    expect((root.querySelector("#legend-bar") as HTMLElement).style.background).toBe(probe.style.background);
    expect(root.querySelector(".no-data")?.textContent).toBe("No station or no ratio");
  });

  test("says what the flat colour is: the mean of the stations of the municipality, and the columns are the stations", () => {
    renderLegend(root, "air", "ignored");

    expect(root.querySelector(".note")?.textContent).toBe("Columns: stations. Ground: mean of the stations of each municipality.");
  });

  test("the emissions have no such note", () => {
    renderLegend(root, "emissions", "1 t/km²");

    expect(root.querySelector(".note")).toBeNull();
  });

  test("the density of the emissions is not in it", () => {
    renderLegend(root, "air", "57 t/km²");

    expect(root.textContent).not.toContain("57");
    expect(root.textContent).not.toContain("km²");
  });
});

describe("changing the view", () => {
  test("replaces the legend: nothing of the other one is left", () => {
    renderLegend(root, "emissions", "57 t/km²");
    renderLegend(root, "air", "x");
    expect(root.querySelectorAll("#legend-bar")).toHaveLength(1);
    expect(root.textContent).not.toContain("Declared per km²");

    renderLegend(root, "emissions", "3 t/km²");
    expect(root.querySelectorAll("#legend-bar")).toHaveLength(1);
    expect(root.textContent).not.toContain("WHO guideline");
    expect(root.getAttribute("aria-label")).toBe("Colour of the units");
  });

  test("the text that comes in is text, never HTML", () => {
    renderLegend(root, "emissions", '<img src=x onerror="window.__legend = 1">');

    expect(root.querySelector("img")).toBeNull();
    expect((window as unknown as { __legend?: number }).__legend).toBeUndefined();
  });
});
