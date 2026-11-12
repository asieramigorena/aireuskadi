// What the person uses to choose the map: a switch between the map of the emissions and the map of
// the air quality, and, in the second one, the pollutant. They are links with an address (so that a
// link can be shared, opened in another tab, and Back works), and the page takes the click.
import { AIR_POLLUTANT_CODES, airPollutantName } from "./format";
import { LANGUAGES, texts, textsOf, type Language } from "./i18n";
import { DEFAULT_POLLUTANT, homeUrl, unitUrl, type Selection, type View } from "./router";

const VIEWS: View[] = ["emissions", "air"];

/** A click that the page takes for itself: a click with a key or another button is the browser's
 * (another tab, another window). */
const isPlainClick = (event: MouseEvent) =>
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
 * The names are the ones of the language in use. */
export function renderControls(
  root: HTMLElement,
  selection: Selection,
  unit: string | null,
  navigate: (url: string) => void,
  station: number | null = null,
): void {
  keepingFocus(root, () => build(root, selection, unit, navigate, station));
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

  if (selection.view !== "air") return;
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
