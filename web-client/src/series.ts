// The series of a pollutant at a station, in its block of the panel: the last 24 hours (the value of
// each hour) or the last 7 or 30 days (the mean of each day), with the WHO guideline as a line. The
// same numbers go in a table that only screen readers read.
import { CategoryScale, Chart, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip, type ChartDataset } from "chart.js";
import { airPollutantName, formatHour, formatMeasure } from "./format";
import { texts } from "./i18n";
import type { StationReading, StationSeries, UnitStation } from "./types";

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Legend, Tooltip);

// The charts that are drawn: the panel destroys them before it is drawn again (main.ts), as it does
// with the chart of the trend, so that none is left behind on a canvas that is gone.
const charts = new Set<Chart>();

export function destroySeriesCharts(): void {
  for (const chart of charts) chart.destroy();
  charts.clear();
}

export type Period = "day" | "week" | "month";
const PERIODS: Period[] = ["day", "week", "month"];
const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

export interface SeriesRange {
  from: string;
  to: string;
  interval: "hour" | "day";
}

/** Asks the series of a pollutant at a station for a range (GET /stations/{id}/measurements). */
export type SeriesFn = (stationId: number, pollutant: string, range: SeriesRange) => Promise<StationSeries>;

/** The range of a period up to `now`: from the start of the hour a day before, by the hour (so 24
 * hours and the minutes of this one); 7 or 30 UTC days (today is the last one, partial) by the day,
 * whose mean is what the WHO guideline of 24 hours is about. */
export function seriesRange(period: Period, now: Date): SeriesRange {
  const to = now.toISOString();
  if (period === "day") {
    const from = new Date(Math.floor(now.getTime() / HOUR) * HOUR - 24 * HOUR);
    return { from: from.toISOString(), to, interval: "hour" };
  }
  const days = period === "week" ? 7 : 30;
  const today = Math.floor(now.getTime() / DAY) * DAY;
  return { from: new Date(today - (days - 1) * DAY).toISOString(), to, interval: "day" };
}

export interface SeriesPoint {
  ts: string;
  value: number;
  /** A day with fewer than 18 hours measured. */
  partial: boolean;
}

export function seriesPoints(series: StationSeries): SeriesPoint[] {
  return series.points.map((point) => ({ ts: point.ts, value: point.value, partial: point.coverage_ok === false }));
}

/** The WHO guideline that a reading is compared with, if its pollutant has one. */
export function guidelineOf(reading: StationReading): { value: number; period: "24h" | "8h" } | null {
  if (reading.who_guideline_ugm3 === null || reading.who_period === null) return null;
  return { value: reading.who_guideline_ugm3, period: reading.who_period };
}

/** "25 Nov" for a day; "25 Nov, 14:00 UTC" for an hour. */
function label(ts: string, interval: "hour" | "day"): string {
  if (interval === "hour") return formatHour(ts);
  const date = new Date(ts);
  return `${date.getUTCDate()} ${texts().months[date.getUTCMonth()]}`;
}

function labelled(text: string, field: HTMLElement): HTMLLabelElement {
  const element = document.createElement("label");
  element.append(text, field);
  return element;
}

/** The button that opens the series and, once opened, the choice of pollutant and period, the chart,
 * the notes and the hidden table. `names` are the names of the pollutants of the card; the series
 * starts with the pollutant of the map if the station measures it. `now` is a function for the tests. */
export function seriesSection(
  station: UnitStation,
  names: ReadonlyMap<string, string>,
  mapPollutant: string,
  load: SeriesFn,
  now: () => Date = () => new Date(),
): HTMLElement {
  const t = texts();
  const section = document.createElement("div");
  section.className = "series";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "open-series";
  open.textContent = t.seriesButton;
  section.append(open);

  const readings = station.readings;
  const pollutant = document.createElement("select");
  pollutant.className = "pollutant";
  for (const reading of readings) {
    const option = document.createElement("option");
    option.value = reading.pollutant;
    option.textContent = airPollutantName(reading.pollutant, names);
    pollutant.append(option);
  }
  pollutant.value = readings.some((reading) => reading.pollutant === mapPollutant) ? mapPollutant : readings[0]?.pollutant ?? "";
  const period = document.createElement("select");
  period.className = "period";
  for (const item of PERIODS) {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = t.seriesPeriods[item];
    period.append(option);
  }
  const box = document.createElement("div");
  box.className = "series-chart";
  const canvas = document.createElement("canvas");
  box.append(canvas);
  const guideline = document.createElement("p");
  guideline.className = "note";
  const note = document.createElement("p");
  note.className = "note";
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  // There from the start, so that a screen reader announces what is written in it later.
  section.append(status);
  const hidden = document.createElement("div");
  hidden.className = "visually-hidden";
  let chart: Chart | null = null;
  // Only the answer of the last choice is shown: an older one that arrives later is left out.
  let asked = 0;

  const clear = () => {
    chart?.destroy();
    if (chart) charts.delete(chart);
    chart = null;
    guideline.textContent = note.textContent = "";
    hidden.replaceChildren();
  };

  const show = async () => {
    const reading = readings.find((item) => item.pollutant === pollutant.value);
    if (!reading) return;
    const mine = ++asked;
    const range = seriesRange(period.value as Period, now());
    status.textContent = t.loading;
    try {
      const points = seriesPoints(await load(station.id, reading.pollutant, range));
      if (mine !== asked) return;
      clear();
      const line = guidelineOf(reading);
      // An 8-hour guideline is about the worst 8 hours of a day: not drawn against daily means.
      const drawn = line && !(line.period === "8h" && range.interval === "day") ? line : null;
      status.textContent = points.length ? "" : t.seriesEmpty;
      guideline.textContent = line ? t.seriesGuideline(line.period, formatMeasure(line.value, "µg/m3")) : t.seriesNoGuideline;
      if (line && !drawn) guideline.textContent += ` ${t.seriesEightHourDaily}`;
      note.textContent = range.interval === "day" ? t.seriesDailyNote : line ? t.seriesHourlyNote : "";
      hidden.replaceChildren(seriesTable(points, range.interval, airPollutantName(reading.pollutant, names)));
      // A panel drawn again while the answer came has a canvas that is no longer on the page.
      if (canvas.isConnected) chart = drawSeriesChart(canvas, points, range.interval, drawn?.value ?? null);
      if (chart) charts.add(chart);
    } catch {
      if (mine !== asked) return;
      clear();
      status.textContent = t.serviceUnavailable;
    }
  };

  open.addEventListener("click", () => {
    open.hidden = true;
    status.before(labelled(t.seriesPollutantLabel, pollutant), labelled(t.seriesPeriodLabel, period), box, guideline, note);
    section.append(hidden);
    pollutant.focus();
    void show();
  });
  pollutant.addEventListener("change", () => void show());
  period.addEventListener("change", () => void show());
  return section;
}

/** The numbers of the chart, for the screen readers. */
function seriesTable(points: SeriesPoint[], interval: "hour" | "day", name: string): HTMLTableElement {
  const t = texts();
  const table = document.createElement("table");
  const caption = document.createElement("caption");
  caption.textContent = t.seriesTableCaption(name);
  const head = document.createElement("tr");
  for (const title of [t.seriesTime, t.seriesValue]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = title;
    head.append(cell);
  }
  const body = document.createElement("tbody");
  for (const point of points) {
    const row = document.createElement("tr");
    const time = document.createElement("th");
    time.scope = "row";
    time.textContent = label(point.ts, interval);
    const value = document.createElement("td");
    value.textContent = formatMeasure(point.value, "µg/m3");
    row.append(time, value);
    body.append(row);
  }
  const thead = document.createElement("thead");
  thead.append(head);
  table.append(caption, thead, body);
  return table;
}

/** The line of the values and, if there is one, the WHO guideline as a dashed line. A partial day
 * is a hollow point. */
function drawSeriesChart(canvas: HTMLCanvasElement, points: SeriesPoint[], interval: "hour" | "day", guideline: number | null): Chart | null {
  // Without a 2D context (an old browser, the tests) there is only the table.
  if (!canvas.getContext?.("2d")) return null;
  const t = texts();
  const datasets: ChartDataset<"line", number[]>[] = [
    {
      label: t.seriesValue,
      data: points.map((point) => point.value),
      borderColor: "#1d6f8a",
      backgroundColor: points.map((point) => (point.partial ? "#ffffff" : "#1d6f8a")),
      pointRadius: 3,
      tension: 0.2,
    },
  ];
  if (guideline !== null) {
    datasets.push({
      label: t.seriesWhoLabel,
      data: points.map(() => guideline),
      borderColor: "#d1374e",
      backgroundColor: "#d1374e",
      pointRadius: 0,
      tension: 0,
      borderDash: [6, 4],
    });
  }
  return new Chart(canvas, {
    type: "line",
    data: { labels: points.map((point) => label(point.ts, interval)), datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: { y: { beginAtZero: true, ticks: { callback: (value) => formatMeasure(Number(value), "µg/m3") } } },
      plugins: { legend: { display: false } },
    },
  });
}
