// SPA entry point: it joins the router, the calls to the gateway, the map and the panel.
import "../styles/style.css";
import { ApiError, createApi } from "./api";
import { errorText, formatDensity, mapCaption } from "./format";
import { HEXAGON_MAX_RADIUS, hexRadiusForZoom } from "./hexagons";
import { buildLayers } from "./layers";
import { levelForZoom } from "./levels";
import { createMap } from "./map";
import { renderPanel, type PanelView } from "./panel";
import { createRouter, homeUrl, unitUrl, type Selection, type State } from "./router";
import { legendGradient, maxDensity } from "./scale";
import type { Level, Point, UnitCollection } from "./types";
import { insetFor } from "./view";

const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const api = createApi();
const panel = element("panel");
const status = element("status");

let selection: Selection | null = null;
let level: Level;
let points: Point[] = [];
let units: UnitCollection | null = null;
// The size of the hexagons follows the zoom (hexagons.ts); the map is drawn again when it changes.
let hexRadius = HEXAGON_MAX_RADIUS;

// The units of a level and a selection are asked for once: going back and forth between zooms
// does not ask again.
const unitCache = new Map<string, UnitCollection>();
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
    void loadUnits();
  }
});
level = levelForZoom(map.initialZoom);
hexRadius = hexRadiusForZoom(map.initialZoom);

function say(text: string) {
  status.textContent = text;
}

function draw() {
  map.setLayers(buildLayers(points, units, (code) => router.navigate(unitUrl(code, selection!)), hexRadius));
  const max = units ? maxDensity(units.features) : 0;
  element("legend-max").textContent = formatDensity(max);
  element("attribution").textContent = units?.attribution ?? "";
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
  renderPanel(panel, view, selection!, () => router.navigate(homeUrl(selection!)));
  fitMapToPanel();
}

function failure(error: unknown) {
  if ((error as Error).name === "AbortError") return;
  const api = error as ApiError;
  say(errorText(api.status ?? 0, api.message));
}

/** The points and the units of the level, in parallel: the map is drawn when both have arrived. */
async function loadMap() {
  mapLoad.abort();
  mapLoad = new AbortController();
  const { signal } = mapLoad;
  say("Loading the map…");
  try {
    [points, units] = await Promise.all([
      api.points(selection!, signal),
      cachedUnits(signal),
    ]);
    say("");
    draw();
  } catch (error) {
    points = [];
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
  const key = `${level}|${selection!.pollutant}|${selection!.year}`;
  const known = unitCache.get(key);
  if (known) return known;
  const fresh = await api.units(level, selection!, signal);
  unitCache.set(key, fresh);
  return fresh;
}

async function showUnit(code: string) {
  cardLoad.abort();
  cardLoad = new AbortController();
  showPanel({ status: "loading" });
  try {
    showPanel({ status: "card", card: await api.unit(code, cardLoad.signal) });
  } catch (error) {
    if ((error as Error).name === "AbortError") return;
    const failed = error as ApiError;
    showPanel({ status: "error", message: errorText(failed.status ?? 0, failed.message) });
  }
}

function onState(state: State) {
  const changed =
    !selection ||
    selection.pollutant !== state.selection.pollutant ||
    selection.year !== state.selection.year;
  selection = state.selection;
  if (changed) {
    element("caption").textContent = mapCaption(selection);
    void loadMap();
  }

  cardLoad.abort();
  if (state.route.name === "unit") {
    void showUnit(state.route.code);
  } else if (state.route.name === "not-found") {
    showPanel({ status: "error", message: "This page does not exist." });
  } else {
    showPanel({ status: "closed" });
  }
}

element("legend-bar").style.background = legendGradient();
// The panel changes place when the screen turns or changes size.
window.addEventListener("resize", fitMapToPanel);
const router = createRouter(window, onState);
router.start();
