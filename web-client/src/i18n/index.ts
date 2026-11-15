// The language of the page: which ones there are, which one a visitor gets, and the texts of the one
// that is in use. The functions of the page that write a text ask for it here when they write it, so
// that drawing the page again in another language is all that changing it takes.
import { en } from "./en";
import { es } from "./es";
import { eu } from "./eu";
import type { Language, Texts } from "./types";

export type { AirCode, Language, Texts } from "./types";

/** In the order that the selector shows them. */
export const LANGUAGES: readonly Language[] = ["eu", "es", "en"];

const DICTIONARIES: Record<Language, Texts> = { eu, es, en };

export const isLanguage = (value: string): value is Language => (LANGUAGES as readonly string[]).includes(value);

/** The language that a browser asks for: the first one of its list (`navigator.languages`) that the
 * page has, whatever the region ("es-419" is Spanish), and English for a visitor who asks for none of
 * them. What is not a language tag is skipped. */
export function detectLanguage(preferred: readonly string[]): Language {
  for (const tag of preferred) {
    if (typeof tag !== "string") continue;
    const primary = tag.trim().toLowerCase().split("-")[0];
    if (isLanguage(primary)) return primary;
  }
  return "en";
}

// English until the page chooses: the tests of everything that writes a text read English.
let current: Language = "en";

export const language = (): Language => current;
export const setLanguage = (next: Language): void => {
  current = next;
};

/** The dictionary of a language, which is not the one in use. */
export const textsOf = (code: Language): Texts => DICTIONARIES[code];

/** The texts of the language in use. */
export const texts = (): Texts => DICTIONARIES[current];
