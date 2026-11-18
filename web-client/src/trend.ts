// The trend of the inventory 1990-2024 in the panel: the tonnes of a pollutant in the whole Basque
// Country, year by year, split by sector. Chart.js draws it; what it says in words (the title, the
// totals of the first and the last year, the notes) is written here, so that it can be read without
// seeing the chart.
import { BarController, BarElement, CategoryScale, Chart, Legend, LinearScale, Tooltip } from "chart.js";
import { ApiError } from "./api";
import { isPlainClick } from "./controls";
import { formatTonnes } from "./format";
import { texts } from "./i18n";
import { trendUrl, type Classification, type Selection } from "./router";
import type { Inventory } from "./types";

// Only the pieces of Chart.js that a bar chart uses: the rest stays out of the bundle.
Chart.register(BarController, BarElement, CategoryScale, LinearScale, Legend, Tooltip);

/** The pollutants of the inventory, in the order of its sheets; methane is only a total. */
export const INVENTORY_POLLUTANTS = ["NOX", "SOX", "NH3", "NMVOC", "CO", "TSP", "PM10", "PM25", "CH4"];

export interface TrendSeries {
  years: number[];
  /** One per sector, with its tonnes in each year of `years` (0 if it has none that year). */
  sectors: { code: string; name: string; values: number[] }[];
}

const own = (table: Record<string, string>, key: string) => (Object.hasOwn(table, key) ? table[key] : undefined);

/** The chart's data: every year once, and one line per sector in the order the API gives them. */
export function trendSeries(inventory: Inventory): TrendSeries {
  const years = [...new Set(inventory.series.map((point) => point.year))].sort((a, b) => a - b);
  const sectors: TrendSeries["sectors"] = [];
  for (const point of inventory.series) {
    let sector = sectors.find((known) => known.code === point.sector.code);
    if (!sector) {
      const name = own(texts().sectors, `${inventory.classification}-${point.sector.code}`) ?? point.sector.name;
      sector = { code: point.sector.code, name, values: years.map(() => 0) };
      sectors.push(sector);
    }
    sector.values[years.indexOf(point.year)] = point.value;
  }
  return { years, sectors };
}

/** The inventory of the pollutant by the sectors that are chosen; methane is only published as a
 * total. null when the inventory has nothing of the pollutant (the API answers 404). */
export async function loadTrend(
  api: { inventory: (pollutant: string, classification: string, signal?: AbortSignal) => Promise<Inventory> },
  pollutant: string,
  classification: Classification,
  signal?: AbortSignal,
): Promise<Inventory | null> {
  try {
    return await api.inventory(pollutant, pollutant === "CH4" ? "TOTAL" : classification, signal);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Which control of the trend has the focus of the keyboard, to give it back after the panel is
 * drawn again (each choice draws it again). */
export function focusedTrendControl(root: HTMLElement): "pollutant" | "sectors" | null {
  const active = document.activeElement;
  if (!active || !root.contains(active)) return null;
  if (active.matches(".trend select")) return "pollutant";
  if (active.matches("a.sectors")) return "sectors";
  return null;
}

export function restoreTrendFocus(root: HTMLElement, which: "pollutant" | "sectors" | null): void {
  if (which === "pollutant") root.querySelector<HTMLElement>(".trend select")?.focus();
  // The sectors that were chosen are the ones that are marked now.
  if (which === "sectors") root.querySelector<HTMLElement>("a.sectors[aria-current='true']")?.focus();
}

/** The name of a pollutant of the inventory in the language of the page (its code otherwise). */
export const inventoryPollutantName = (code: string) => own(texts().inventoryPollutants, code) ?? code;

/** The title of the panel: the pollutant and the years that the inventory has. */
export function trendTitle(pollutant: string, inventory: Inventory | null): string {
  const name = inventoryPollutantName(pollutant);
  if (!inventory || inventory.series.length === 0) return name;
  const { years } = trendSeries(inventory);
  return texts().trendTitle(name, years[0], years[years.length - 1]);
}

function paragraph(text: string, className?: string): HTMLParagraphElement {
  const node = document.createElement("p");
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

/** What goes in the panel under its title: the choice of the pollutant and of the sectors, the
 * notes, the place of the chart (a canvas that `drawTrendChart` fills) and the credit. */
export function trendSection(
  inventory: Inventory | null,
  selection: Selection,
  classification: Classification,
  navigate: (url: string) => void,
): HTMLElement {
  const section = document.createElement("section");
  section.className = "trend";

  const choice = document.createElement("select");
  choice.setAttribute("aria-label", texts().inventoryPollutantLabel);
  const codes = INVENTORY_POLLUTANTS.includes(selection.pollutant) ? INVENTORY_POLLUTANTS : [...INVENTORY_POLLUTANTS, selection.pollutant];
  for (const code of codes) {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = inventoryPollutantName(code);
    choice.append(option);
  }
  choice.value = selection.pollutant;
  choice.addEventListener("change", () => navigate(trendUrl({ ...selection, pollutant: choice.value }, classification)));
  section.append(choice);

  // Methane has no sectors: there is nothing to choose.
  if (selection.pollutant !== "CH4") {
    const choices = document.createElement("nav");
    choices.setAttribute("aria-label", texts().sectorsLabel);
    for (const kind of ["SNAP", "NFR"] as const) {
      const link = document.createElement("a");
      link.className = "sectors";
      link.textContent = kind;
      link.setAttribute("href", trendUrl(selection, kind));
      if (kind === classification) link.setAttribute("aria-current", "true");
      link.addEventListener("click", (event) => {
        if (!isPlainClick(event)) return;
        event.preventDefault();
        navigate(trendUrl(selection, kind));
      });
      choices.append(link);
    }
    section.append(choices);
  }

  if (!inventory || inventory.series.length === 0) {
    section.append(paragraph(texts().noInventory, "none"));
    return section;
  }
  if (selection.pollutant === "CH4") section.append(paragraph(texts().methaneTotalOnly, "note"));
  if (classification === "NFR" && selection.pollutant === "TSP") section.append(paragraph(texts().nfrParticlesNote, "note"));

  // The chart is a picture: its words are the totals of the first and the last year.
  const { years, sectors } = trendSeries(inventory);
  const total = (index: number) => sectors.reduce((sum, sector) => sum + sector.values[index], 0);
  const last = years.length - 1;
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", texts().trendSummary(formatTonnes(total(0)), years[0], formatTonnes(total(last)), years[last]));
  const box = document.createElement("div");
  box.className = "chart";
  box.append(canvas);
  section.append(box, lastYearTable(sectors, years[last], last), paragraph(inventory.attribution, "credit"));
  return section;
}

/** The split of the last year in words, for whoever does not see the chart: a table that is read
 * aloud but not shown. */
function lastYearTable(sectors: TrendSeries["sectors"], year: number, index: number): HTMLTableElement {
  const table = document.createElement("table");
  table.className = "visually-hidden";
  const caption = document.createElement("caption");
  caption.textContent = texts().trendTableCaption(year);
  const body = document.createElement("tbody");
  for (const sector of sectors) {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    name.textContent = sector.name;
    const value = document.createElement("td");
    value.textContent = formatTonnes(sector.values[index]);
    row.append(name, value);
    body.append(row);
  }
  table.append(caption, body);
  return table;
}

// One colour per sector, enough for the 11 SNAP ones: each one at least 3:1 against the pale panel,
// and a white line between the parts of a bar so that two neighbours are told apart.
const COLOURS = ["#1f6f8b", "#b5502b", "#3d405b", "#3b7a57", "#8a6100", "#6d597a", "#a03e58", "#2f5f86", "#1b7470", "#6b5a00", "#4f596b"];

/** Draws the stacked bars of the series in the canvas; the caller destroys the chart before the
 * panel is drawn again. */
export function drawTrendChart(canvas: HTMLCanvasElement, series: TrendSeries): Chart {
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: series.years.map(String),
      datasets: series.sectors.map((sector, index) => ({
        label: sector.name,
        data: sector.values,
        backgroundColor: COLOURS[index % COLOURS.length],
        borderColor: "#ffffff",
        borderWidth: 1,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { stacked: true },
        y: { stacked: true, ticks: { callback: (value) => formatTonnes(Number(value)) } },
      },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
    },
  });
}
