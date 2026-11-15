// The panel of a unit. Everything that comes from the API (names of units and of pollutants, the
// detail of an error) is written with `textContent`, never as HTML: it is free text.
import {
  airPollutantName,
  emissionName,
  formatArea,
  formatDensity,
  formatHour,
  formatMeasure,
  formatRatio,
  formatReadingRatio,
  formatTonnes,
} from "./format";
import { texts } from "./i18n";
import type { Selection } from "./router";
import type { UnitAirQuality, UnitCard, UnitStation } from "./types";

export type PanelView =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "error"; message: string }
  // `station` is the id of the station that the person chose on the map: it is shown open, at the top.
  | { status: "card"; card: UnitCard; station?: number | null };

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
  close.setAttribute("aria-label", texts().closePanel);
  close.addEventListener("click", onClose);
  bar.append(element("h2", title), close);
  return bar;
}

function emissionsTable(card: UnitCard, selection: Selection): HTMLElement {
  const rows = card.emissions.filter((emission) => emission.year === selection.year);
  if (rows.length === 0) {
    return element("p", texts().noEmissions(selection.year));
  }
  const table = element("table");
  table.append(element("caption", texts().emissionsCaption(selection.year)));
  // The ratio with the WHO guideline is only there when there is one to show: while no pollutant
  // has it, the column would be "No data" in every row and would take the width of the others.
  const withRatio = rows.some((emission) => emission.who_ratio !== null);
  const head = element("tr");
  const { columns } = texts();
  for (const title of [columns.pollutant, columns.declared, columns.perKm2, ...(withRatio ? [columns.guideline] : [])]) {
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
    // The row of the pollutant that the map shows; the map of the air quality shows another thing.
    if (selection.view === "emissions" && emission.pollutant === selection.pollutant) {
      row.setAttribute("aria-current", "true");
    }
    const name = element("th", emissionName(emission.pollutant, emission.name));
    name.scope = "row";
    row.append(
      name,
      element("td", formatTonnes(emission.declared_t)),
      element("td", formatDensity(emission.t_km2)),
    );
    if (withRatio) row.append(element("td", formatRatio(emission.who_ratio), "ratio"));
    body.append(row);
  }
  table.append(body);
  return table;
}

/** Why there is nothing to show, in words: the API gives only a code. An own property of the table
 * only, so that a code that is the name of something that every object has (like "toString") finds
 * nothing and the generic text is said. */
function noMeasurement(reason: string | null): string {
  const table: Record<string, string> = texts().noMeasurement;
  return reason !== null && reason !== "other" && Object.hasOwn(table, reason) ? table[reason] : table.other;
}

function stationBlock(
  station: UnitStation,
  open: boolean,
  chosen: boolean,
  names: ReadonlyMap<string, string>,
): HTMLElement {
  const block = element("details");
  block.open = open || chosen;
  // The station of the map that was clicked: marked like the pollutant of the map in the emissions.
  if (chosen) block.setAttribute("aria-current", "true");
  block.append(element("summary", station.name));
  if (station.readings.length === 0) {
    block.append(element("p", texts().noValues, "none"));
    return block;
  }
  // A loop and not Math.max(...list): a list that is long enough cannot be spread.
  const newest = station.readings.reduce((latest, reading) => Math.max(latest, Date.parse(reading.ts)), -Infinity);
  block.append(element("p", texts().latestValue(formatHour(new Date(newest).toISOString())), "updated"));

  const table = element("table", undefined, "readings");
  const head = element("tr");
  const { columns } = texts();
  for (const title of [columns.pollutant, columns.latest, columns.guideline]) {
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

function airQualitySection(air: UnitAirQuality | null, card: UnitCard, chosen: number | null): HTMLElement {
  const section = element("section", undefined, "air-quality");
  section.append(element("h3", texts().airQuality));
  if (air === null) {
    section.append(element("p", texts().airUnavailable, "none"));
    return section;
  }
  if (!air.measured) section.append(element("p", noMeasurement(air.reason), "none"));
  const stations = air.stations ?? [];
  const names = new Map(card.emissions.map((emission) => [emission.pollutant, emissionName(emission.pollutant, emission.name)]));
  // One station is shown open; a list of them is closed so that the names can be read at once.
  for (const station of stations) {
    section.append(stationBlock(station, stations.length === 1, station.id === chosen, names));
  }
  if (air.measured) section.append(element("p", air.attribution, "source"));
  return section;
}

/** The section of the air quality, which can never take the card down with it: it comes from another
 * service, and the name of the unit and its emissions are what the panel is for. Whatever is wrong
 * with it (a time that is not a time, a list that is not a list), the section says it is not
 * available. */
function airQualityOf(card: UnitCard, chosen: number | null): HTMLElement {
  try {
    return airQualitySection(card.air_quality, card, chosen);
  } catch {
    return airQualitySection(null, card, null);
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
      root.append(header(texts().loading, onClose));
      return;
    case "error": {
      root.append(header(texts().somethingWrong, onClose));
      const alert = element("p", view.message);
      alert.setAttribute("role", "alert");
      root.append(alert);
      return;
    }
    case "card": {
      const { card } = view;
      root.append(header(card.name, onClose));
      const places = [texts().kinds[card.level], card.district?.name, card.territory?.name, formatArea(card.area_km2)];
      root.append(element("p", places.filter(Boolean).join(" · "), "meta"));
      // What the map shows comes first: the table of emissions or the stations.
      const emissions = emissionsTable(card, selection);
      const airQuality = airQualityOf(card, view.station ?? null);
      root.append(...(selection.view === "air" ? [airQuality, emissions] : [emissions, airQuality]));
      // The panel can be short (a phone) and the list long: the station that was chosen is brought
      // to the top of the panel, under the header that stays there (scroll-padding-top).
      airQuality.querySelector("details[aria-current='true']")?.scrollIntoView?.({ block: "start" });
    }
  }
}
