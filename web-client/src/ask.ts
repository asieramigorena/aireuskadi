// The box in a corner of the map that asks a language model about the unit (GET /units/{code}/insight) or about
// what a value means (GET /insights/{topic}). The questions are a fixed list: nothing is typed but
// the key. Only someone logged in can ask, with a provider of the list and their own key, which stays
// in the memory of this tab (never in localStorage, sessionStorage or a cookie).
import { ApiError, type createApi } from "./api";
import { airPollutantName, emissionName } from "./format";
import { language, texts } from "./i18n";
import type { Language } from "./i18n/types";
import type { Selection } from "./router";
import type { Insight, LlmChoice, UnitCard, UnitQuestion } from "./types";

/** Asks one question of the list (its key) with the choice of the person, and gives the text. */
export type AskFn = (question: string, llm: LlmChoice) => Promise<Insight>;

/** The models that a key can use at a provider (GET /api/v1/llm/models). */
export type ModelsFn = (provider: string, key: string) => Promise<string[]>;

/** The providers of the list (the gateway accepts only these ids) and a model to start with. */
export const PROVIDERS = [
  { id: "groq", name: "Groq", model: "openai/gpt-oss-120b" },
  { id: "openrouter", name: "OpenRouter", model: "openrouter/free" },
  { id: "gemini", name: "Google Gemini", model: "gemini-2.5-flash-lite" },
  { id: "mistral", name: "Mistral", model: "mistral-small-latest" },
  { id: "ollama", name: "Ollama Cloud", model: "gpt-oss:120b" },
  { id: "openai", name: "OpenAI", model: "gpt-5-mini" },
];

// What the person chose and typed: in the memory of the page only, so it is kept while they move
// from one unit to another and is gone when the tab is closed or reloaded.
const choice: LlmChoice = { provider: PROVIDERS[0].id, model: PROVIDERS[0].model, key: "" };
// The models of the provider that the key can use, once the provider has said them (else empty).
let models: string[] = [];

const UNIT_QUESTIONS: readonly string[] = ["summary", "meaning"];

/** A question of the list; `needsUnit`: it is about one unit, so it waits until one is open. */
export interface QuestionItem {
  key: string;
  label: string;
  needsUnit: boolean;
}

/** The questions of the box: the two about a unit (they need one open), the two general ones, and
 * "what is ...?" for the pollutant of the map and, with a unit open, for every pollutant that its
 * stations measure, once each, in the order of their names. Not every pollutant of the emissions: a
 * big municipality declares 30 or 40. */
export function questionsOf(card: UnitCard | null, year: number, mapPollutant: string): QuestionItem[] {
  const t = texts();
  const emitted = new Map<string, string>();
  for (const emission of card?.emissions ?? []) {
    if (emission.year === year) emitted.set(emission.pollutant, emissionName(emission.pollutant, emission.name));
  }
  const names = new Map<string, string>();
  for (const station of card?.air_quality?.stations ?? []) {
    for (const reading of station.readings) names.set(reading.pollutant, airPollutantName(reading.pollutant, emitted));
  }
  // The pollutant of the map: with a unit, only if the unit has it; without one, always.
  const shown = card ? emitted.get(mapPollutant) : airPollutantName(mapPollutant);
  if (shown && !names.has(mapPollutant)) names.set(mapPollutant, shown);
  const pollutants = [...names].sort(([, a], [, b]) => a.localeCompare(b));
  return [
    { key: "summary", label: t.questionSummary, needsUnit: true },
    { key: "meaning", label: t.questionMeaning, needsUnit: true },
    { key: "who_ratio", label: t.questionWhoRatio, needsUnit: false },
    { key: "density", label: t.questionDensity, needsUnit: false },
    ...pollutants.map(([code, name]) => ({ key: `pollutant:${code}`, label: t.questionPollutant(name), needsUnit: false })),
  ];
}

/** Sends a question to its route: the ones about the unit with its code and the year of the map, the
 * general ones only with the language (their text is the same for every unit). */
export function askFor(
  api: ReturnType<typeof createApi>,
  code: string,
  question: string,
  lang: Language,
  year: number,
  llm: LlmChoice,
): Promise<Insight> {
  return UNIT_QUESTIONS.includes(question)
    ? api.insight(code, question as UnitQuestion, lang, year, llm)
    : api.generalInsight(question, lang, llm);
}

/** A label with its text and the field inside. */
function labelled(text: string, field: HTMLElement): HTMLLabelElement {
  const label = document.createElement("label");
  label.append(text, field);
  return label;
}

/** For someone who is not logged in: the two ways in, in the language of the page. */
function logInFirst(): HTMLElement {
  const t = texts();
  const paragraph = document.createElement("p");
  paragraph.textContent = `${t.askLogIn} `;
  for (const [path, words] of [["/user", t.askLogInLink], ["/user/signup", t.askSignUpLink]]) {
    const link = document.createElement("a");
    link.href = `${path}?lang=${language()}`;
    link.textContent = words;
    paragraph.append(link, " ");
  }
  return paragraph;
}

// Whether the box is open: kept while the page is drawn again (another unit, another pollutant).
let boxOpen = false;

/** Draws the box of the questions in `root`, a corner of the map that is always there: a line that
 * opens it and, inside, for someone logged in, the provider, the model, the key, the list of questions,
 * the button, the line that says how it goes and the answer. `card` is the unit whose panel is open,
 * or null: then the questions about a unit are shown in another colour and cannot be chosen.
 * `account` is the name of who is logged in, or null. */
export function renderAsk(
  root: HTMLElement,
  card: UnitCard | null,
  selection: Selection,
  ask: AskFn,
  account: string | null,
  listModels: ModelsFn,
) {
  const t = texts();
  const details = document.createElement("details");
  details.open = boxOpen;
  details.addEventListener("toggle", () => (boxOpen = details.open));
  const summary = document.createElement("summary");
  summary.textContent = t.askTitle;
  details.append(summary);
  root.replaceChildren(details);
  // Which unit the questions about a unit are about, or how to choose one.
  const about = document.createElement("p");
  about.className = "about";
  about.textContent = card ? t.askHeading(card.name) : t.askChooseUnit;
  details.append(about);
  if (account === null) {
    details.append(logInFirst());
    return;
  }

  const provider = document.createElement("select");
  provider.className = "provider";
  for (const item of PROVIDERS) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    provider.append(option);
  }
  provider.value = choice.provider;
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  // The models that exist for this key: a list, so that nobody asks one that does not exist. Until
  // the provider says them (the key is needed for that), only the one to start with.
  const model = document.createElement("select");
  model.className = "model";
  const fillModels = () => {
    const names = models.length ? models : [choice.model];
    if (!names.includes(choice.model)) choice.model = names[0];
    model.replaceChildren(
      ...names.map((name) => {
        const option = document.createElement("option");
        option.value = option.textContent = name;
        return option;
      }),
    );
    model.value = choice.model;
  };
  fillModels();
  const key = document.createElement("input");
  key.type = "password";
  key.autocomplete = "off";
  key.value = choice.key;
  const keyNote = document.createElement("p");
  keyNote.className = "note";
  keyNote.textContent = t.keyNote;
  // Asks the provider which models the key can use (when there is a key).
  const loadModels = async () => {
    if (!choice.key) return;
    status.textContent = t.askLoadingModels;
    try {
      models = await listModels(choice.provider, choice.key);
      fillModels();
      status.textContent = "";
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) status.replaceChildren(...logInFirst().childNodes);
      else status.textContent = failure(error);
    }
  };
  // A new provider brings its own model to start with, and its own list; what is chosen is
  // remembered in the page.
  provider.addEventListener("change", () => {
    choice.provider = provider.value;
    choice.model = PROVIDERS.find((item) => item.id === provider.value)?.model ?? "";
    models = [];
    fillModels();
    void loadModels();
  });
  model.addEventListener("change", () => (choice.model = model.value));
  // The models are asked half a second after the key stops changing: while it is typed or pasted,
  // without leaving the field.
  let waiting: ReturnType<typeof setTimeout> | undefined;
  key.addEventListener("input", () => {
    choice.key = key.value.trim();
    models = [];
    clearTimeout(waiting);
    waiting = setTimeout(() => void loadModels(), 500);
  });
  // A key that was typed before (the box is drawn again for another unit) and has no list yet.
  if (choice.key && !models.length) void loadModels();

  const question = document.createElement("select");
  question.className = "question";
  question.setAttribute("aria-label", t.askChoiceLabel);
  for (const item of questionsOf(card, selection.year, selection.pollutant)) {
    const option = document.createElement("option");
    option.value = item.key;
    // Without a unit, the questions about one are there, in another colour, but cannot be chosen.
    const waits = item.needsUnit && !card;
    option.textContent = waits ? `${item.label} (${t.askNeedsUnit})` : item.label;
    option.disabled = waits;
    if (item.needsUnit) option.className = "needs-unit";
    question.append(option);
  }
  // The first question that can be asked is the one chosen to start with.
  question.value = [...question.options].find((option) => !option.disabled)?.value ?? "";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = t.askButton;
  const answer = document.createElement("p");
  answer.className = "answer";
  const note = document.createElement("p");
  note.className = "note";

  button.addEventListener("click", async () => {
    // Without a key nothing is sent: the gateway would only refuse it.
    if (!choice.key) {
      status.textContent = t.askNeedKey;
      return;
    }
    button.disabled = true;
    status.textContent = t.askWriting;
    answer.textContent = "";
    note.textContent = "";
    try {
      // What the model wrote is text, never HTML.
      answer.textContent = (await ask(question.value, { ...choice })).text;
      note.textContent = t.generatedNote;
      status.textContent = "";
    } catch (error) {
      // The session ended (401): the same words and the two ways in as for someone logged out.
      if (error instanceof ApiError && error.status === 401) status.replaceChildren(...logInFirst().childNodes);
      else status.textContent = failure(error);
    } finally {
      button.disabled = false;
    }
  });

  details.append(
    labelled(t.providerLabel, provider),
    labelled(t.modelLabel, model),
    labelled(t.keyLabel, key),
    keyNote,
    question,
    button,
    status,
    answer,
    note,
  );
}

/** Why a question failed, in words: never what the server wrote. */
function failure(error: unknown): string {
  const t = texts();
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 429) return t.askTooMany;
  if (status === 403) return t.askKeyRefused;
  return t.askNotAvailable;
}
