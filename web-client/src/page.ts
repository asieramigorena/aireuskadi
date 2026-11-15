// The texts of index.html that nothing else draws: the labels of the parts of the page, the credits,
// and the language of the whole document. They are written again each time the language or the map
// changes. Text only: nothing here is HTML.
import { language, texts } from "./i18n";
import { mapLabel } from "./format";
import type { View } from "./router";

const byId = (id: string) => document.getElementById(id);

function label(id: string, text: string): void {
  byId(id)?.setAttribute("aria-label", text);
}

/** Writes them for the language in use and the map that is shown. `stationsAttribution` is the credit
 * that the stations come with, once they have arrived. */
export function applyPageTexts(view: View, stationsAttribution: string | null): void {
  const words = texts();
  document.documentElement.lang = language();
  label("controls", words.mapChoiceLabel);
  label("languages", words.languageChoiceLabel);
  label("panel", words.panelLabel);
  label("map", mapLabel(view));

  // The credit of what the map shows: the emissions, or the stations.
  const emissionsCredit = byId("emissions-credit");
  if (emissionsCredit) {
    emissionsCredit.textContent = words.emissionsCredit;
    emissionsCredit.hidden = view === "air";
  }
  const airCredit = byId("air-credit");
  if (airCredit) {
    airCredit.textContent = view === "air" && stationsAttribution ? words.airCredit(stationsAttribution) : "";
  }
}
