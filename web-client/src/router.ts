// The router: which screen the URL asks for, and the History API so that Back works. The view of
// the map, its pollutant and its year live in the query of the URL, so a link shows what the person
// saw.

/** `station` is the id of the station of the unit that is open in its panel, if the address says one:
 * a click on a station of the map of the air quality opens its unit with that station shown. */
export type Route =
  | { name: "home" }
  | { name: "unit"; code: string; station: number | null }
  | { name: "not-found" };

/** The map of the declared emissions, or the map of the air quality that the stations measure. */
export type View = "emissions" | "air";

export interface Selection {
  view: View;
  pollutant: string;
  /** Of the emissions. The air quality is the latest value of each station: it has no year. */
  year: number;
}

export interface State {
  route: Route;
  selection: Selection;
}

export const DEFAULT_SELECTION: Selection = { view: "emissions", pollutant: "NOX", year: 2023 };

/** The pollutant of each view when the URL does not say one: the two do not measure the same. */
export const DEFAULT_POLLUTANT: Record<View, string> = { emissions: "NOX", air: "NO2" };

// The same shapes that the API accepts: a pollutant code of capitals, digits and underscore, and
// the code of a territory (2 digits), a district (4) or a municipality (5). A value that does not
// fit is not sent anywhere: it is the default one, or the page is not found.
const POLLUTANT = /^[A-Z0-9_]{1,20}$/;
const YEAR = /^[0-9]{1,4}$/;
// An id of a station: digits, no zero in front (the air quality service takes it that way).
const STATION = /^[1-9][0-9]{0,9}$/;
const UNIT_PATH = /^\/unit\/([0-9]{2}|[0-9]{4}|[0-9]{5})$/;

export function parseLocation(pathname: string, search: string): State {
  const query = new URLSearchParams(search);
  const view: View = query.get("view") === "air" ? "air" : "emissions";
  const pollutant = query.get("pollutant") ?? "";
  const year = query.get("year") ?? "";
  const selection: Selection = {
    view,
    pollutant: POLLUTANT.test(pollutant) ? pollutant : DEFAULT_POLLUTANT[view],
    year: YEAR.test(year) && Number(year) >= 1 ? Number(year) : DEFAULT_SELECTION.year,
  };

  if (pathname === "/") return { route: { name: "home" }, selection };
  const unit = UNIT_PATH.exec(pathname);
  if (unit) {
    const station = query.get("station") ?? "";
    return { route: { name: "unit", code: unit[1], station: STATION.test(station) ? Number(station) : null }, selection };
  }
  return { route: { name: "not-found" }, selection };
}

function selectionQuery(selection: Selection): string {
  const query = new URLSearchParams();
  if (selection.view === "air") query.set("view", "air");
  if (selection.pollutant !== DEFAULT_POLLUTANT[selection.view]) query.set("pollutant", selection.pollutant);
  // Only the emissions have a year.
  if (selection.view === "emissions" && selection.year !== DEFAULT_SELECTION.year) {
    query.set("year", String(selection.year));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

/** The address of a unit. `station` is only kept in the map of the air quality, the one that has them. */
export function unitUrl(code: string, selection: Selection, station: number | null = null): string {
  const query = new URLSearchParams(selectionQuery(selection));
  if (selection.view === "air" && station !== null) query.set("station", String(station));
  const text = query.toString();
  return `/unit/${code}${text ? `?${text}` : ""}`;
}

export const homeUrl = (selection: Selection) => `/${selectionQuery(selection)}`;

export function createRouter(win: Window, onChange: (state: State) => void) {
  const read = () => parseLocation(win.location.pathname, win.location.search);
  const here = () => win.location.pathname + win.location.search;

  return {
    start() {
      win.addEventListener("popstate", () => onChange(read()));
      onChange(read());
    },
    navigate(url: string) {
      // Only the addresses of the application: the code of a unit or the id of a station comes from
      // the API, and nothing that it says takes the page to another site or to a path of nothing.
      const target = new URL(url, win.location.href);
      if (target.origin !== win.location.origin) return;
      if (parseLocation(target.pathname, target.search).route.name === "not-found") return;
      const next = target.pathname + target.search;
      if (next === here()) return;
      win.history.pushState(null, "", next);
      onChange(read());
    },
  };
}
