// The panel of a unit. Everything that comes from the API (names of units and of pollutants, the
// detail of an error) is written with `textContent`, never as HTML: it is free text.
import {
  airPollutantName,
  formatArea,
  formatDensity,
  formatHour,
  formatMeasure,
  formatRatio,
  formatReadingRatio,
  formatTonnes,
} from "./format";
import type { Selection } from "./router";
import type { UnitAirQuality, UnitCard, UnitStation } from "./types";

export type PanelView =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "card"; card: UnitCard };

const KIND = { municipality: "Municipality", district: "District", territory: "Territory" };

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

function header(title: string, onClose: () => void): HTMLElement {
  const bar = element("header");
  const close = element("button", "×");
  close.type = "button";
  close.setAttribute("aria-label", "Close the panel");
  close.addEventListener("click", onClose);
  bar.append(element("h2", title), close);
  return bar;
}

function emissionsTable(card: UnitCard, selection: Selection): HTMLElement {
  const rows = card.emissions.filter((emission) => emission.year === selection.year);
  if (rows.length === 0) {
    return element("p", `No declared emissions in ${selection.year}.`);
  }
  const table = element("table");
  table.append(element("caption", `Declared industrial emissions in ${selection.year}`));
  // The ratio with the WHO guideline is only there when there is one to show: while no pollutant
  // has it, the column would be "No data" in every row and would take the width of the others.
  const withRatio = rows.some((emission) => emission.who_ratio !== null);
  const head = element("tr");
  for (const title of ["Pollutant", "Declared", "Per km²", ...(withRatio ? ["WHO guideline"] : [])]) {
    const cell = element("th", title);
    cell.scope = "col";
    head.append(cell);
  }
  const thead = element("thead");
  thead.append(head);
  table.append(thead);
  const body = element("tbody");
  for (const emission of rows) {
    const row = element("tr");
    if (emission.pollutant === selection.pollutant) row.setAttribute("aria-current", "true");
    const name = element("th", emission.name);
    name.scope = "row";
    row.append(
      name,
      element("td", formatTonnes(emission.declared_t)),
      element("td", formatDensity(emission.t_km2)),
    );
    if (withRatio) row.append(element("td", formatRatio(emission.who_ratio)));
    body.append(row);
  }
  table.append(body);
  return table;
}

const NOT_AVAILABLE = "Air quality is not available right now.";

// Why there is nothing to show, in words: the API gives only a code. A Map, so that a code that is
// the name of something that every object has (like "toString") finds nothing.
const NO_MEASUREMENT = new Map([
  ["no_station", "There is no air quality station in this municipality."],
  ["no_data", "The stations of this municipality have no values yet."],
  ["level_not_supported", "Stations are shown for municipalities: choose one to see its air quality."],
]);

function stationBlock(station: UnitStation, open: boolean, names: ReadonlyMap<string, string>): HTMLElement {
  const block = element("details");
  block.open = open;
  block.append(element("summary", station.name));
  if (station.readings.length === 0) {
    block.append(element("p", "No values yet.", "none"));
    return block;
  }
  // A loop and not Math.max(...list): a list that is long enough cannot be spread.
  const newest = station.readings.reduce((latest, reading) => Math.max(latest, Date.parse(reading.ts)), -Infinity);
  block.append(element("p", `Latest value: ${formatHour(new Date(newest).toISOString())}`, "updated"));

  const table = element("table", undefined, "readings");
  const head = element("tr");
  for (const title of ["Pollutant", "Latest", "WHO guideline"]) {
    const cell = element("th", title);
    cell.scope = "col";
    head.append(cell);
  }
  const thead = element("thead");
  thead.append(head);
  table.append(thead);
  const body = element("tbody");
  for (const reading of station.readings) {
    const row = element("tr");
    const name = element("th", airPollutantName(reading.pollutant, names));
    name.scope = "row";
    // The value and its unit are kept in one line (.measure); a value that is older than the latest
    // one of the station says its own time after it.
    const value = element("td");
    value.append(element("span", formatMeasure(reading.value, reading.unit), "measure"));
    if (Date.parse(reading.ts) < newest) value.append(` (${formatHour(reading.ts)})`);
    row.append(name, value, element("td", formatReadingRatio(reading)));
    body.append(row);
  }
  table.append(body);
  block.append(table);
  return block;
}

function airQualitySection(air: UnitAirQuality | null, card: UnitCard): HTMLElement {
  const section = element("section", undefined, "air-quality");
  section.append(element("h3", "Air quality"));
  if (air === null) {
    section.append(element("p", NOT_AVAILABLE, "none"));
    return section;
  }
  if (!air.measured) {
    const reason = air.reason ? NO_MEASUREMENT.get(air.reason) : undefined;
    section.append(element("p", reason ?? "There is no air quality to show for this unit.", "none"));
  }
  const stations = air.stations ?? [];
  const names = new Map(card.emissions.map((emission) => [emission.pollutant, emission.name]));
  // One station is shown open; a list of them is closed so that the names can be read at once.
  for (const station of stations) section.append(stationBlock(station, stations.length === 1, names));
  if (air.measured) section.append(element("p", air.attribution, "source"));
  return section;
}

/** The section of the air quality, which can never take the card down with it: it comes from another
 * service, and the name of the unit and its emissions are what the panel is for. Whatever is wrong
 * with it (a time that is not a time, a list that is not a list), the section says it is not
 * available. */
function airQualityOf(card: UnitCard): HTMLElement {
  try {
    return airQualitySection(card.air_quality, card);
  } catch {
    return airQualitySection(null, card);
  }
}

export function renderPanel(
  root: HTMLElement,
  view: PanelView,
  selection: Selection,
  onClose: () => void,
): void {
  root.replaceChildren();
  root.hidden = view.status === "closed";
  root.setAttribute("aria-busy", String(view.status === "loading"));

  switch (view.status) {
    case "closed":
      return;
    case "loading":
      root.append(header("Loading…", onClose));
      return;
    case "error": {
      root.append(header("Something went wrong", onClose));
      const alert = element("p", view.message);
      alert.setAttribute("role", "alert");
      root.append(alert);
      return;
    }
    case "card": {
      const { card } = view;
      root.append(header(card.name, onClose));
      const places = [KIND[card.level], card.district?.name, card.territory?.name, formatArea(card.area_km2)];
      root.append(element("p", places.filter(Boolean).join(" · "), "meta"));
      root.append(emissionsTable(card, selection));
      root.append(airQualityOf(card));
    }
  }
}
