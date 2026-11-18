// What the person uses to choose the map: a switch between the map of the emissions and the map of
// the air quality, and, in the second one, the pollutant. They are links with an address (so that a
// link can be shared, opened in another tab, and Back works), and the page takes the click.
import { AIR_POLLUTANT_CODES, airPollutantName, emissionName } from "./format";
import { LANGUAGES, language, texts, textsOf, type Language } from "./i18n";
import { DEFAULT_POLLUTANT, homeUrl, trendUrl, unitUrl, type Selection, type View } from "./router";
import type { PollutantName } from "./types";

/** What the map of the emissions can be drawn for: the years and the pollutants that the API says. */
export interface Choices {
  years: number[];
  pollutants: PollutantName[];
}

const NO_CHOICES: Choices = { years: [], pollutants: [] };

const VIEWS: View[] = ["emissions", "air"];

/** A click that the page takes for itself: a click with a key or another button is the browser's
 * (another tab, another window). */
export const isPlainClick = (event: MouseEvent) =>
  event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;

/** The focus of the keyboard stays where it was when the controls are drawn again: choosing with the
 * keyboard draws them again, and the control that had the focus would be gone and the focus would
 * fall to the page. If the control that had it is gone (the selector of the air, back to the
 * emissions), it goes to the last one that is left. */
function keepingFocus(root: HTMLElement, draw: () => void): void {
  const controls = () => [...root.querySelectorAll<HTMLElement>("a, select")];
  const focused = controls().indexOf(document.activeElement as HTMLElement);
  draw();
  if (focused >= 0) {
    const now = controls();
    now[Math.min(focused, now.length - 1)]?.focus();
  }
}

/** Writes the controls in `root`, in place of the ones that were there. `unit` is the code of the
 * unit whose panel is open, if any, and `station` the one that is shown in it: the controls keep
 * them, so that only the map changes (the emissions have no stations: the address drops it).
 * `choices` are the pollutants and the years with emissions (the API says them); without them there
 * is no selector of them. The names are the ones of the language in use. */
export function renderControls(
  root: HTMLElement,
  selection: Selection,
  unit: string | null,
  navigate: (url: string) => void,
  station: number | null = null,
  choices: Choices = NO_CHOICES,
): void {
  keepingFocus(root, () => build(root, selection, unit, navigate, station, choices));
}

/** Writes the selector of the language in `root`: a link for each language, with its code as the text
 * and its name as the title. Each is an address that keeps the map, the unit and the station, and
 * says the language, so that a link that is shared keeps it. `current` is the one in use. */
export function renderLanguages(
  root: HTMLElement,
  current: Language,
  selection: Selection,
  unit: string | null,
  navigate: (url: string) => void,
  station: number | null = null,
): void {
  keepingFocus(root, () => {
    root.replaceChildren();
    for (const code of LANGUAGES) {
      const url = unit ? unitUrl(unit, { ...selection, lang: code }, station) : homeUrl({ ...selection, lang: code });
      const link = document.createElement("a");
      link.textContent = code.toUpperCase();
      link.setAttribute("href", url);
      link.setAttribute("lang", code);
      link.setAttribute("title", textsOf(code).languageName);
      link.setAttribute("aria-label", textsOf(code).languageName);
      if (code === current) link.setAttribute("aria-current", "true");
      link.addEventListener("click", (event) => {
        if (!isPlainClick(event)) return;
        event.preventDefault();
        navigate(url);
      });
      root.append(link);
    }
  });
}

function build(
  root: HTMLElement,
  selection: Selection,
  unit: string | null,
  navigate: (url: string) => void,
  station: number | null,
  choices: Choices,
): void {
  const urlOf = (chosen: Selection) => (unit ? unitUrl(unit, chosen, station) : homeUrl(chosen));
  root.replaceChildren();

  for (const view of VIEWS) {
    const link = document.createElement("a");
    link.textContent = view === "emissions" ? texts().viewEmissions : texts().viewAir;
    // The map that is shown keeps its pollutant; the other one starts with its own.
    const target: Selection = view === selection.view ? selection : { ...selection, view, pollutant: DEFAULT_POLLUTANT[view] };
    link.setAttribute("href", urlOf(target));
    if (view === selection.view) link.setAttribute("aria-current", "true");
    link.addEventListener("click", (event) => {
      if (!isPlainClick(event)) return;
      event.preventDefault();
      navigate(urlOf(target));
    });
    root.append(link);
  }

  if (selection.view === "emissions") {
    if (choices.pollutants.length > 0) {
      root.append(pollutantChoice(selection, choices.pollutants, (pollutant) => navigate(urlOf({ ...selection, pollutant }))));
    }
    if (choices.years.length > 0) {
      root.append(yearChoice(selection, choices.years, (year) => navigate(urlOf({ ...selection, year }))));
    }
    // The trend of the inventory opens in the panel, over the map of the emissions.
    const trend = document.createElement("a");
    trend.className = "trend-link";
    trend.textContent = texts().trendLink;
    trend.setAttribute("href", trendUrl(selection, "SNAP"));
    trend.addEventListener("click", (event) => {
      if (!isPlainClick(event)) return;
      event.preventDefault();
      navigate(trendUrl(selection, "SNAP"));
    });
    root.append(trend);
    return;
  }
  const choice = document.createElement("select");
  choice.setAttribute("aria-label", texts().airPollutantLabel);
  const codes = AIR_POLLUTANT_CODES.includes(selection.pollutant) ? AIR_POLLUTANT_CODES : [...AIR_POLLUTANT_CODES, selection.pollutant];
  for (const code of codes) {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = airPollutantName(code);
    choice.append(option);
  }
  choice.value = selection.pollutant;
  choice.addEventListener("change", () => navigate(urlOf({ ...selection, pollutant: choice.value })));
  root.append(choice);
}

/** The selector of the year of the emissions: the newest first. A year that the address says and
 * that is not in the list is added, so that the selector never says another year than the map. */
function yearChoice(selection: Selection, years: number[], choose: (year: number) => void): HTMLSelectElement {
  const choice = document.createElement("select");
  choice.setAttribute("aria-label", texts().yearLabel);
  const shown = years.includes(selection.year) ? years : [...years, selection.year];
  for (const year of [...shown].sort((a, b) => b - a)) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    choice.append(option);
  }
  choice.value = String(selection.year);
  choice.addEventListener("change", () => choose(Number(choice.value)));
  return choice;
}

/** The selector of the pollutant of the emissions, by the name in the language of the page in its
 * alphabetical order. A pollutant that the address says and that is not in the list is added. */
function pollutantChoice(selection: Selection, pollutants: PollutantName[], choose: (code: string) => void): HTMLSelectElement {
  const choice = document.createElement("select");
  choice.className = "emission-pollutant";
  choice.setAttribute("aria-label", texts().emissionPollutantLabel);
  const named = pollutants.map((pollutant) => ({ code: pollutant.code, name: emissionName(pollutant.code, pollutant.name) }));
  if (!named.some((pollutant) => pollutant.code === selection.pollutant)) {
    named.push({ code: selection.pollutant, name: selection.pollutant });
  }
  named.sort((a, b) => a.name.localeCompare(b.name, language()));
  for (const pollutant of named) {
    const option = document.createElement("option");
    option.value = pollutant.code;
    option.textContent = pollutant.name;
    choice.append(option);
  }
  choice.value = selection.pollutant;
  choice.addEventListener("change", () => choose(choice.value));
  return choice;
}
