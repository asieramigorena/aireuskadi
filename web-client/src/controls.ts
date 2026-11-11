// What the person uses to choose the map: a switch between the map of the emissions and the map of
// the air quality, and, in the second one, the pollutant. They are links with an address (so that a
// link can be shared, opened in another tab, and Back works), and the page takes the click.
import { AIR_POLLUTANT_CODES, airPollutantName } from "./format";
import { DEFAULT_POLLUTANT, homeUrl, unitUrl, type Selection, type View } from "./router";

const VIEWS: { view: View; name: string }[] = [
  { view: "emissions", name: "Emissions" },
  { view: "air", name: "Air quality" },
];

/** Writes the controls in `root`, in place of the ones that were there. `unit` is the code of the
 * unit whose panel is open, if any, and `station` the one that is shown in it: the controls keep
 * them, so that only the map changes (the emissions have no stations: the address drops it).
 * The focus of the keyboard stays where it was: choosing a map or a pollutant draws the controls
 * again, and the control that had the focus would be gone and the focus would fall to the page. */
export function renderControls(
  root: HTMLElement,
  selection: Selection,
  unit: string | null,
  navigate: (url: string) => void,
  station: number | null = null,
): void {
  const controls = () => [...root.querySelectorAll<HTMLElement>("a, select")];
  const focused = controls().indexOf(document.activeElement as HTMLElement);
  build(root, selection, unit, navigate, station);
  if (focused >= 0) {
    const now = controls();
    // If the control that had it is gone (the selector of the air, back to the emissions), the last.
    now[Math.min(focused, now.length - 1)]?.focus();
  }
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

  for (const { view, name } of VIEWS) {
    const link = document.createElement("a");
    link.textContent = name;
    // The map that is shown keeps its pollutant; the other one starts with its own.
    const target: Selection = view === selection.view ? selection : { ...selection, view, pollutant: DEFAULT_POLLUTANT[view] };
    link.setAttribute("href", urlOf(target));
    if (view === selection.view) link.setAttribute("aria-current", "true");
    link.addEventListener("click", (event) => {
      // A click with a key or another button is the browser's: another tab, another window.
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      navigate(urlOf(target));
    });
    root.append(link);
  }

  if (selection.view !== "air") return;
  const choice = document.createElement("select");
  choice.setAttribute("aria-label", "Pollutant of the air quality");
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
