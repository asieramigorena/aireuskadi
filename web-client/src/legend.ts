// The legend of the map: what the colours mean in each view. It is built here and not written in
// index.html because the two maps have different scales; everything that comes in is text.
import { texts } from "./i18n";
import type { View } from "./router";
import { legendGradient, ratioLegendGradient } from "./scale";

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function bar(gradient: string): HTMLElement {
  const node = element("div");
  node.id = "legend-bar";
  node.style.background = gradient;
  return node;
}

function ends(...labels: string[]): HTMLElement {
  const node = element("div", undefined, "legend-ends");
  node.append(...labels.map((label) => element("span", label)));
  return node;
}

function grey(text: string): HTMLElement {
  const node = element("p", undefined, "no-data");
  node.append(element("span", undefined, "swatch"), text);
  return node;
}

/** Writes the legend of `view` in `root`, in place of the one that was there. `densityMax` is the
 * biggest density of the emissions, already written ("57 t/km²"); the air quality does not use it. */
export function renderLegend(root: HTMLElement, view: View, densityMax: string): void {
  root.replaceChildren();
  const words = texts();
  if (view === "emissions") {
    root.setAttribute("aria-label", words.legendUnitsLabel);
    root.append(element("p", words.legendDensity), bar(legendGradient()), ends("0", densityMax), grey(words.noData));
    return;
  }
  root.setAttribute("aria-label", words.legendStationsLabel);
  // The tick is the guideline itself: the middle of the bar, since the scale goes from 0 to twice it.
  const scale = bar(ratioLegendGradient());
  scale.append(element("span", undefined, "legend-tick"));
  const labels = ends("0", words.legendGuideline, words.legendTwiceOrMore);
  labels.classList.add("three");
  root.append(
    element("p", words.legendRatioTitle),
    scale,
    labels,
    element("p", words.legendNote, "note"),
    grey(words.legendNoStationOrRatio),
  );
}
