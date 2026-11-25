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
// The name of who is logged in (from /user/me, asked once by main.ts), or null.
let accountName: string | null = null;

export function setAccountName(name: string | null) {
  accountName = name;
}

export function applyPageTexts(view: View, stationsAttribution: string | null): void {
  const words = texts();
  document.documentElement.lang = language();
  label("controls", words.mapChoiceLabel);
  label("languages", words.languageChoiceLabel);
  label("panel", words.panelLabel);
  label("map", mapLabel(view));

  // The way in to the accounts: a plain link to the login page (/user, with the sign-up), which the
  // auth service makes, in the language of the map. Someone logged in sees their name: the same
  // page is then their account, with the way out.
  const loginLink = byId("login-link");
  if (loginLink) {
    loginLink.textContent = accountName ?? words.loginLink;
    loginLink.setAttribute("href", `/user?lang=${language()}`);
  }

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
