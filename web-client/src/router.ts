// The router: which screen the URL asks for, and the History API so that Back works. The pollutant
// and the year of the map live in the query of the URL, so a link shows what the person saw.

export type Route = { name: "home" } | { name: "unit"; code: string } | { name: "not-found" };

export interface Selection {
  pollutant: string;
  year: number;
}

export interface State {
  route: Route;
  selection: Selection;
}

export const DEFAULT_SELECTION: Selection = { pollutant: "NOX", year: 2023 };

// The same shapes that the API accepts: a pollutant code of capitals, digits and underscore, and
// the code of a territory (2 digits), a district (4) or a municipality (5). A value that does not
// fit is not sent anywhere: it is the default one, or the page is not found.
const POLLUTANT = /^[A-Z0-9_]{1,20}$/;
const YEAR = /^[0-9]{1,4}$/;
const UNIT_PATH = /^\/unit\/([0-9]{2}|[0-9]{4}|[0-9]{5})$/;

export function parseLocation(pathname: string, search: string): State {
  const query = new URLSearchParams(search);
  const pollutant = query.get("pollutant") ?? "";
  const year = query.get("year") ?? "";
  const selection: Selection = {
    pollutant: POLLUTANT.test(pollutant) ? pollutant : DEFAULT_SELECTION.pollutant,
    year: YEAR.test(year) && Number(year) >= 1 ? Number(year) : DEFAULT_SELECTION.year,
  };

  if (pathname === "/") return { route: { name: "home" }, selection };
  const unit = UNIT_PATH.exec(pathname);
  if (unit) return { route: { name: "unit", code: unit[1] }, selection };
  return { route: { name: "not-found" }, selection };
}

function selectionQuery(selection: Selection): string {
  const query = new URLSearchParams();
  if (selection.pollutant !== DEFAULT_SELECTION.pollutant) query.set("pollutant", selection.pollutant);
  if (selection.year !== DEFAULT_SELECTION.year) query.set("year", String(selection.year));
  const text = query.toString();
  return text ? `?${text}` : "";
}

export const unitUrl = (code: string, selection: Selection) =>
  `/unit/${code}${selectionQuery(selection)}`;

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
      if (url === here()) return;
      win.history.pushState(null, "", url);
      onChange(read());
    },
  };
}
