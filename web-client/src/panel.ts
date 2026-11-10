// The panel of a unit. Everything that comes from the API (names of units and of pollutants, the
// detail of an error) is written with `textContent`, never as HTML: it is free text.
import { formatArea, formatDensity, formatRatio, formatTonnes } from "./format";
import type { Selection } from "./router";
import type { UnitCard } from "./types";

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
    }
  }
}
