// SPA entry point: it joins the router, the calls to the gateway, the map and the panel.
import "../styles/style.css";
import { createApi, failureText } from "./api";
import { renderControls, renderLanguages, type Choices } from "./controls";
import { formatDensity, mapCaption } from "./format";
import { HEXAGON_MAX_RADIUS, hexRadiusForZoom } from "./hexagons";
import { buildAirLayers, buildLayers } from "./layers";
import { createStatus } from "./status";
import { detectLanguage, language, setLanguage, texts, type Language } from "./i18n";
import { levelForZoom } from "./levels";
import { renderLegend } from "./legend";
import { createMap } from "./map";
import { applyPageTexts } from "./page";
import { renderPanel, type PanelView } from "./panel";
import { createRouter, homeUrl, parseLocation, setDefaultYear, unitUrl, type Classification, type Selection, type State } from "./router";
import { maxDensity } from "./scale";
import type { BoundaryCollection, Level, Point, StationCollection, UnitCollection, UnitIndicators } from "./types";
import { drawTrendChart, focusedTrendControl, loadTrend, restoreTrendFocus, trendSeries } from "./trend";
import { withIndicators } from "./units";
import { insetFor } from "./view";

const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const api = createApi();
const panel = element("panel");
const status = element("status");

let selection: Selection | null = null;
let level: Level;
let points: Point[] = [];
let stations: StationCollection | null = null;
let units: UnitCollection | null = null;
// The size of the hexagons follows the zoom (hexagons.ts); the map is drawn again when it changes.
let hexRadius = HEXAGON_MAX_RADIUS;
let legendShown = "";
// The years and the pollutants with emissions, for their selectors: asked once (see the end of the
// file).
let choices: Choices = { years: [], pollutants: [] };
let lastState: State | null = null;

// What is asked for once: the boundaries of each level (the same for every pollutant and year) and
// the numbers of each level, pollutant and year. Going back and forth between zooms or pollutants
// does not ask again.
const boundaryCache = new Map<Level, BoundaryCollection>();
const indicatorCache = new Map<string, UnitIndicators[]>();
// The chart of the trend that is drawn, if any: it is destroyed before the panel changes.
let chart: { destroy(): void } | null = null;
let mapLoad = new AbortController();
let cardLoad = new AbortController();

const map = createMap(element<HTMLDivElement>("map"), (zoom) => {
  const radius = hexRadiusForZoom(zoom);
  if (radius !== hexRadius) {
    hexRadius = radius;
    draw();
  }
  const wanted = levelForZoom(zoom);
  if (wanted !== level && selection) {
    level = wanted;
    // The ground of the air quality is always the municipalities: the zoom does not change it.
    if (selection.view !== "air") void loadUnits();
  }
});
level = levelForZoom(map.initialZoom);
hexRadius = hexRadiusForZoom(map.initialZoom);

const line = createStatus(status);
const say = line.say;

function draw() {
  const air = selection!.view === "air";
  const onUnit = (code: string, station?: number) => router.navigate(unitUrl(code, selection!, station ?? null));
  map.setLayers(
    air ? buildAirLayers(stations, units, onUnit, hexRadius) : buildLayers(points, units, onUnit, hexRadius),
  );
  // The legend is drawn again only when it says something else (the zoom draws the map often).
  const legend = `${selection!.view}|${formatDensity(units ? maxDensity(units.features) : 0)}`;
  if (legend !== legendShown) {
    legendShown = legend;
    renderLegend(element("legend"), selection!.view, formatDensity(units ? maxDensity(units.features) : 0));
  }
  element("attribution").textContent = units?.attribution ?? "";
  element("app").classList.toggle("air-view", air);
  // The credit of what the map shows (the emissions, or the stations once they have arrived).
  applyPageTexts(selection!.view, stations?.attribution ?? null);
}

/** Centre the map in what the panel leaves free. The layout box is read (not the one that is
 * drawn): the panel slides in, and while it moves its drawn box is not where it will stay. */
function fitMapToPanel() {
  const open = !panel.hidden;
  const box = open
    ? { left: panel.offsetLeft, top: panel.offsetTop, width: panel.offsetWidth, height: panel.offsetHeight }
    : null;
  map.setInset(insetFor(box, window.innerWidth, window.innerHeight));
}

function showPanel(view: PanelView) {
  chart?.destroy();
  chart = null;
  renderPanel(panel, view, selection!, () => router.navigate(homeUrl(selection!)), (url) => router.navigate(url));
  fitMapToPanel();
}

function failure(error: unknown) {
  if (failureText(error) !== null) say(() => failureText(error) ?? "");
}

/** What the map shows, and the units of the level, in parallel: the map is drawn when both have
 * arrived. The emissions are the points of the facilities; the air quality, the stations. */
async function loadMap() {
  mapLoad.abort();
  mapLoad = new AbortController();
  const { signal } = mapLoad;
  say(() => texts().loadingMap);
  try {
    if (selection!.view === "air") {
      // Apart: if only the stations fail (a pollutant that they do not have), the municipalities are
      // still drawn, and the status line says what happened.
      const [fromStations, fromUnits] = await Promise.allSettled([
        api.stations(selection!.pollutant, signal),
        cachedUnits(signal),
      ]);
      if (fromUnits.status === "rejected") throw fromUnits.reason;
      units = fromUnits.value;
      points = [];
      if (fromStations.status === "rejected") {
        stations = null;
        draw();
        failure(fromStations.reason);
        return;
      }
      stations = fromStations.value;
    } else {
      [points, units] = await Promise.all([api.points(selection!, signal), cachedUnits(signal)]);
      stations = null;
      // Not an error: no facility declared the pollutant that year. Said, so the map is not just empty.
      if (points.length === 0) {
        say(() => texts().noDataForSelection);
        draw();
        return;
      }
    }
    say(() => "");
    draw();
  } catch (error) {
    // A load that was cancelled by a newer one leaves the map as it is: the newer one draws.
    if (failureText(error) === null) return;
    points = [];
    stations = null;
    units = null;
    draw();
    failure(error);
  }
}

/** Only the units, when the zoom takes the map to another level. */
async function loadUnits() {
  mapLoad.abort();
  mapLoad = new AbortController();
  try {
    units = await cachedUnits(mapLoad.signal);
    draw();
  } catch (error) {
    failure(error);
  }
}

async function cachedUnits(signal: AbortSignal): Promise<UnitCollection> {
  // The map of the air quality draws the units only as ground for its stations: it needs their
  // boundaries and none of the numbers of the emissions. Only the municipalities have stations,
  // so that is its ground at any zoom.
  const air = selection!.view === "air";
  const wanted: Level = air ? "municipality" : level;
  const [shapes, numbers] = await Promise.all([
    cachedBoundaries(wanted, signal),
    air ? Promise.resolve(null) : cachedIndicators(wanted, selection!, signal),
  ]);
  return withIndicators(shapes, numbers);
}

async function cachedBoundaries(wanted: Level, signal: AbortSignal): Promise<BoundaryCollection> {
  const known = boundaryCache.get(wanted);
  if (known) return known;
  const fresh = await api.boundaries(wanted, signal);
  boundaryCache.set(wanted, fresh);
  return fresh;
}

async function cachedIndicators(wanted: Level, chosen: Selection, signal: AbortSignal): Promise<UnitIndicators[]> {
  const key = `${wanted}|${chosen.pollutant}|${chosen.year}`;
  const known = indicatorCache.get(key);
  if (known) return known;
  const fresh = await api.units(wanted, chosen, signal);
  indicatorCache.set(key, fresh);
  return fresh;
}

async function showUnit(code: string, station: number | null) {
  cardLoad.abort();
  cardLoad = new AbortController();
  showPanel({ status: "loading" });
  try {
    // A station is only shown in the map of the air quality, the one that has them.
    const shown = selection!.view === "air" ? station : null;
    showPanel({ status: "card", card: await api.unit(code, cardLoad.signal), station: shown });
  } catch (error) {
    // The same words as the status line: a cancelled call says nothing, and an error of the code is
    // not shown as it is.
    const text = failureText(error);
    if (text !== null) showPanel({ status: "error", message: text });
  }
}

/** The trend of the inventory of the pollutant of the map, in the panel. Methane is only a total. */
async function showTrend(classification: Classification) {
  cardLoad.abort();
  cardLoad = new AbortController();
  // A choice inside the trend keeps the panel as it is while the new one comes (no "loading" in
  // between), and gives the focus of the keyboard back to the control that had it.
  const focused = focusedTrendControl(panel);
  if (!panel.querySelector(".trend")) showPanel({ status: "loading" });
  try {
    const inventory = await loadTrend(api, selection!.pollutant, classification, cardLoad.signal);
    showPanel({ status: "trend", inventory, classification });
    const canvas = panel.querySelector("canvas");
    if (inventory && canvas) chart = drawTrendChart(canvas, trendSeries(inventory));
    restoreTrendFocus(panel, focused);
  } catch (error) {
    const text = failureText(error);
    if (text !== null) showPanel({ status: "error", message: text });
  }
}

function onState(state: State) {
  const first = !selection;
  const dataChanged =
    first ||
    selection!.view !== state.selection.view ||
    selection!.pollutant !== state.selection.pollutant ||
    selection!.year !== state.selection.year;
  const viewChanged = first || selection!.view !== state.selection.view;
  // The language that the person chose; if none, the one that the browser asks for (English if it is
  // neither Basque nor Spanish).
  const wanted = state.selection.lang ?? detectLanguage(navigator.languages?.length ? navigator.languages : [navigator.language]);
  const languageChanged = first || wanted !== language();
  selection = state.selection;
  setLanguage(wanted);

  if (viewChanged) {
    // What the other map showed is not drawn under the caption of this one while it loads.
    points = [];
    stations = null;
  }
  if (dataChanged || languageChanged) {
    // Everything that is written is written again, in the language and for the map that is shown.
    element("caption").textContent = mapCaption(selection, pollutantNames());
    applyPageTexts(selection.view, stations?.attribution ?? null);
    line.refresh();
    legendShown = "";
    if (units) draw();
    else renderLegend(element("legend"), selection.view, formatDensity(0));
  }
  if (dataChanged) void loadMap();

  lastState = state;
  drawControls(state, wanted);

  cardLoad.abort();
  if (state.route.name === "unit") {
    void showUnit(state.route.code, state.route.station);
  } else if (state.route.name === "trend") {
    void showTrend(state.route.classification);
  } else if (state.route.name === "not-found") {
    showPanel({ status: "error", message: texts().pageNotFound });
  } else {
    showPanel({ status: "closed" });
  }
}

/** The controls say the map, the year and the language that are shown, and keep the unit whose panel
 * is open. */
function drawControls(state: State, wanted: Language) {
  const unit = state.route.name === "unit" ? state.route.code : null;
  const chosenStation = state.route.name === "unit" ? state.route.station : null;
  const go = (url: string) => router.navigate(url);
  // With the trend open the year does nothing (the inventory has every year): no selector of it.
  const shown = state.route.name === "trend" ? { ...choices, years: [] } : choices;
  renderControls(element("controls"), state.selection, unit, go, chosenStation, shown);
  renderLanguages(element("languages"), wanted, state.selection, unit, go, chosenStation);
}

// The panel changes place when the screen turns or changes size.
window.addEventListener("resize", fitMapToPanel);
const router = createRouter(window, onState);
router.start();

/** The names of the pollutants of the emissions that the API gave, by code. A function and not a
 * `const`: onState uses it before this line of the file is reached (router.start() runs above). */
function pollutantNames() {
  return new Map(choices.pollutants.map((pollutant) => [pollutant.code, pollutant.name]));
}

// The years and the pollutants come once, each on its own: until one comes (or if it cannot be
// asked) there is no selector of it, and what the address says is still what is shown.
void Promise.allSettled([api.years(), api.pollutants()]).then(([years, pollutants]) => {
  choices = {
    years: years.status === "fulfilled" ? years.value : [],
    pollutants: pollutants.status === "fulfilled" ? pollutants.value : [],
  };
  if (!lastState) return;
  if (choices.years.length) {
    // An address without a year shows the newest one: now that it is known, the address is read
    // again. An address with a year says the same as before, and nothing is drawn again.
    setDefaultYear(Math.max(...choices.years));
    const again = parseLocation(window.location.pathname, window.location.search);
    if (again.selection.year !== lastState.selection.year) onState(again);
  }
  drawControls(lastState, language());
  element("caption").textContent = mapCaption(lastState.selection, pollutantNames());
});
