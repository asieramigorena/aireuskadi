// The calls to the gateway. It is the only place that knows the routes, and the only way out of the
// page: a relative URL, so that every call goes to the site that served the page and never to
// another one.
import type { SeriesRange } from "./series";
import type { BoundaryCollection, Insight, Inventory, LlmChoice, StationSeries, Level, Point, PollutantName, StationCollection, UnitCard, UnitIndicators, UnitQuestion } from "./types";
import type { Language } from "./i18n/types";
import { errorText } from "./format";
import { texts } from "./i18n";
import type { Selection } from "./router";

const PREFIX = "/api/v1";

/** A whole number from 1 to 9999, like the years that the address accepts (router.ts). */
const isYear = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 9999;

/** Something that went wrong with a call. `status` is 0 when the gateway could not be reached. */
export class ApiError extends Error {
  // The message is fixed (for the log): what the service says is not kept, because it is in English
  // and could say things about the inside. The page speaks by the code (`errorText`).
  constructor(readonly status: number) {
    super(`The call failed with status ${status}.`);
    this.name = "ApiError";
  }
}

/** What the status line says when a load fails, in the language of the page: nothing for a call that
 * was cancelled (whoever cancelled it knows), words for the code of an error of the service (what
 * the gateway wrote is in English and is not shown), and a fixed text for anything else: the message
 * of an error of the code ("x is not iterable") says things about the inside and means nothing to the
 * person. */
export function failureText(error: unknown): string | null {
  if (error instanceof DOMException && error.name === "AbortError") return null;
  if (error instanceof ApiError) return errorText(error.status);
  return texts().serviceUnavailable;
}

export function createApi(fetchFn: typeof fetch = (...args) => fetch(...args)) {
  async function get<T>(
    path: string,
    query: Record<string, string>,
    signal?: AbortSignal,
    headers?: Record<string, string>,
  ): Promise<T> {
    const text = new URLSearchParams(query).toString();
    let response: Response;
    try {
      response = await fetchFn(`${PREFIX}${path}${text ? `?${text}` : ""}`, { signal, headers });
    } catch (error) {
      // A cancelled call is not a failure of the service: whoever cancelled it knows.
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0);
    }
    if (!response.ok) throw new ApiError(response.status);
    return (await response.json()) as T;
  }

  const year = (selection: Selection) => String(selection.year);

  return {
    points: (selection: Selection, signal?: AbortSignal) =>
      get<Point[]>("/facilities/points", { pollutant: selection.pollutant, year: year(selection) }, signal),
    /** The numbers of every unit of the level for the pollutant and the year: no boundaries. */
    units: (level: Level, selection: Selection, signal?: AbortSignal) =>
      get<UnitIndicators[]>("/units", { level, pollutant: selection.pollutant, year: year(selection) }, signal),
    /** The boundaries of the units of a level: they weigh, and they do not change with the pollutant. */
    boundaries: (level: Level, signal?: AbortSignal) => get<BoundaryCollection>("/units/boundaries", { level }, signal),
    /** The latest value of each station for a pollutant: the map of the air quality. */
    stations: (pollutant: string, signal?: AbortSignal) =>
      get<StationCollection>("/stations/latest", { pollutant }, signal),
    unit: (code: string, signal?: AbortSignal) => get<UnitCard>(`/units/${encodeURIComponent(code)}`, {}, signal),
    /** The years that have emissions in the register, the oldest first: the years of the map. The
     * newest becomes the year of the map and goes in its addresses, so only what can be a year. */
    years: async (signal?: AbortSignal) =>
      (await get<unknown[]>("/facilities/years", {}, signal)).filter(isYear),
    /** The pollutants that have emissions in the register: the pollutants of the map. */
    pollutants: (signal?: AbortSignal) => get<PollutantName[]>("/facilities/pollutants", {}, signal),
    /** The trend of a pollutant in the inventory, by the sectors of a classification. */
    inventory: (pollutant: string, classification: string, signal?: AbortSignal) =>
      get<Inventory>("/inventory", { pollutant, classification }, signal),
    /** A question about one unit, about its card in the year of the map. The provider and the model
     * go in the address; the key only in a header, so that it is in no address, history or log. */
    insight: (code: string, question: UnitQuestion, lang: Language, year: number, llm: LlmChoice, signal?: AbortSignal) =>
      get<Insight>(
        `/units/${encodeURIComponent(code)}/insight`,
        { question, lang, year: String(year), provider: llm.provider, model: llm.model },
        signal,
        { "X-LLM-Key": llm.key },
      ),
    /** What a value means, the same for every unit: who_ratio, density or pollutant:<CODE>. */
    generalInsight: (topic: string, lang: Language, llm: LlmChoice, signal?: AbortSignal) =>
      get<Insight>(
        `/insights/${encodeURIComponent(topic)}`,
        { lang, provider: llm.provider, model: llm.model },
        signal,
        { "X-LLM-Key": llm.key },
      ),
    /** The series of a pollutant at a station in a range: by the hour, or the mean of each day. */
    stationSeries: (id: number, pollutant: string, range: SeriesRange, signal?: AbortSignal) =>
      get<StationSeries>(`/stations/${id}/measurements`, { pollutant, from: range.from, to: range.to, interval: range.interval }, signal),
    /** The models that the key can use at the provider, for the list of the panel. The key only in a
     * header, as in the questions. */
    models: async (provider: string, key: string, signal?: AbortSignal): Promise<string[]> => {
      const body = await get<{ models: unknown[] }>("/llm/models", { provider }, signal, { "X-LLM-Key": key });
      return body.models.filter((name): name is string => typeof name === "string");
    },
    /** The name of the account that is logged in (the cookie, which the page cannot read), or null:
     * nobody, or the service could not say. */
    me: async (): Promise<string | null> => {
      try {
        const response = await fetchFn("/user/me");
        if (!response.ok) return null;
        const body = await response.json();
        return typeof body?.username === "string" ? body.username : null;
      } catch {
        return null;
      }
    },
  };
}

export type Api = ReturnType<typeof createApi>;
