// The calls to the gateway. It is the only place that knows the routes, and the only way out of the
// page: a relative URL, so that every call goes to the site that served the page and never to
// another one.
import type { Level, Point, UnitCard, UnitCollection } from "./types";
import type { Selection } from "./router";

const PREFIX = "/api/v1";

/** Something that went wrong with a call. `status` is 0 when the gateway could not be reached. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function problemDetail(response: Response): Promise<string> {
  // The gateway answers its errors as problem documents (RFC 9457). Anything else (a page of an
  // intermediary, a crash) is not shown: it says things about the inside.
  if (response.headers.get("content-type")?.includes("application/problem+json")) {
    try {
      const body = await response.json();
      if (typeof body.detail === "string") return body.detail;
    } catch {
      // not a document after all
    }
  }
  return "The service is not available right now.";
}

export function createApi(fetchFn: typeof fetch = (...args) => fetch(...args)) {
  async function get<T>(path: string, query: Record<string, string>, signal?: AbortSignal): Promise<T> {
    const text = new URLSearchParams(query).toString();
    let response: Response;
    try {
      response = await fetchFn(`${PREFIX}${path}${text ? `?${text}` : ""}`, { signal });
    } catch (error) {
      // A cancelled call is not a failure of the service: whoever cancelled it knows.
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, "The service cannot be reached.");
    }
    if (!response.ok) throw new ApiError(response.status, await problemDetail(response));
    return (await response.json()) as T;
  }

  const year = (selection: Selection) => String(selection.year);

  return {
    points: (selection: Selection, signal?: AbortSignal) =>
      get<Point[]>("/facilities/points", { pollutant: selection.pollutant, year: year(selection) }, signal),
    units: (level: Level, selection: Selection, signal?: AbortSignal) =>
      get<UnitCollection>("/units", { level, pollutant: selection.pollutant, year: year(selection) }, signal),
    unit: (code: string, signal?: AbortSignal) => get<UnitCard>(`/units/${encodeURIComponent(code)}`, {}, signal),
  };
}

export type Api = ReturnType<typeof createApi>;
