import { describe, expect, test, vi } from "vitest";
import { ApiError, createApi, failureText } from "../src/api";

const SELECTION = { view: "emissions" as const, pollutant: "NOX", year: 2023 };

function answer(body: unknown, status = 200, type = "application/json") {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": type } });
}

function apiWith(response: Response | Error) {
  const fetchFn = vi.fn(async (_url: string, _options?: RequestInit) => {
    if (response instanceof Error) throw response;
    return response;
  });
  return { api: createApi(fetchFn as unknown as typeof fetch), fetchFn };
}

function urlOf(fetchFn: { mock: { calls: unknown[][] } }): URL {
  return new URL(String(fetchFn.mock.calls[0][0]), "http://page.test");
}

describe("the calls go only to the gateway, to the routes of /api/v1", () => {
  test("the points of the facilities", async () => {
    const { api, fetchFn } = apiWith(answer([[-2.9, 43.2, 1500]]));

    const points = await api.points(SELECTION);

    expect(points).toEqual([[-2.9, 43.2, 1500]]);
    const url = urlOf(fetchFn);
    expect(url.origin).toBe("http://page.test"); // a relative URL: the page itself, not another site
    expect(url.pathname).toBe("/api/v1/facilities/points");
    expect(Object.fromEntries(url.searchParams)).toEqual({ pollutant: "NOX", year: "2023" });
  });

  test("the units of a level", async () => {
    const collection = { type: "FeatureCollection", attribution: "x", features: [] };
    const { api, fetchFn } = apiWith(answer(collection));

    expect(await api.units("district", SELECTION)).toEqual(collection);

    const url = urlOf(fetchFn);
    expect(url.pathname).toBe("/api/v1/units");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      level: "district",
      pollutant: "NOX",
      year: "2023",
    });
  });

  test("the card of one unit", async () => {
    const card = { code: "01036", level: "municipality", name: "Laudio", emissions: [] };
    const { api, fetchFn } = apiWith(answer(card));

    expect(await api.unit("01036")).toEqual(card);

    expect(urlOf(fetchFn).pathname).toBe("/api/v1/units/01036");
  });

  test("the latest value of each station, for a pollutant and nothing else", async () => {
    const collection = { type: "FeatureCollection", attribution: "x", pollutant: "NO2", features: [] };
    const { api, fetchFn } = apiWith(answer(collection));

    expect(await api.stations("NO2")).toEqual(collection);

    const url = urlOf(fetchFn);
    expect(url.origin).toBe("http://page.test");
    expect(url.pathname).toBe("/api/v1/stations/latest");
    expect(Object.fromEntries(url.searchParams)).toEqual({ pollutant: "NO2" });
  });

  test("the pollutant of the stations is a value: it cannot change the path", async () => {
    const { api, fetchFn } = apiWith(answer({}));

    await api.stations("../health?x=1");

    const url = urlOf(fetchFn);
    expect(url.pathname).toBe("/api/v1/stations/latest");
    expect(url.searchParams.get("pollutant")).toBe("../health?x=1");
  });

  test("a code is encoded, so it cannot change the path", async () => {
    const { api, fetchFn } = apiWith(answer({}));

    await api.unit("../health");

    expect(urlOf(fetchFn).pathname).toBe("/api/v1/units/..%2Fhealth");
  });

  test("it only asks with GET and sends nothing of the person", async () => {
    const { api, fetchFn } = apiWith(answer([]));

    await api.points(SELECTION);

    const options = fetchFn.mock.calls[0][1] ?? {};
    expect(options.method ?? "GET").toBe("GET");
    expect(options.credentials ?? "same-origin").toBe("same-origin");
    expect(options.body).toBeUndefined();
  });

  test("the signal is passed on, so that an answer that is no longer wanted can be cancelled", async () => {
    const { api, fetchFn } = apiWith(answer([]));
    const controller = new AbortController();

    await api.points(SELECTION, controller.signal);

    expect(fetchFn.mock.calls[0][1]?.signal).toBe(controller.signal);
  });
});

describe("what goes wrong", () => {
  test("an error of the gateway is an ApiError with its status and the detail of its problem document", async () => {
    const problem = { type: "about:blank", title: "Not Found", status: 404, detail: "Unit 99999 not found." };
    const { api } = apiWith(answer(problem, 404, "application/problem+json"));

    const error = await api.unit("99999").catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.message).toBe("Unit 99999 not found.");
  });

  test("a 422 says what was wrong and does not break the page", async () => {
    const problem = { status: 422, detail: "The request has invalid or missing parameters.", errors: [] };
    const { api } = apiWith(answer(problem, 422, "application/problem+json"));

    const error = await api.points({ view: "emissions", pollutant: "NOX", year: 2099 }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
  });

  test("an answer that is not a problem document gets a fixed message, not the text of the body", async () => {
    const { api } = apiWith(new Response("<html>Traceback: secret</html>", { status: 502 }));

    const error = await api.unit("01036").catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.message).toBe("The service is not available right now.");
    expect(error.message).not.toContain("secret");
  });

  test("a network that fails is an ApiError that says that it cannot be reached", async () => {
    const { api } = apiWith(new TypeError("Failed to fetch"));

    const error = await api.unit("01036").catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.message).toBe("The service cannot be reached.");
  });

  test("a call that was cancelled is not an error of the service: the cancellation is passed on", async () => {
    const cancelled = new DOMException("aborted", "AbortError");
    const { api } = apiWith(cancelled);

    const error = await api.unit("01036").catch((e) => e);

    expect(error).toBe(cancelled);
  });
});

describe("failureText: what the status line says when a load fails", () => {
  test("a call that was cancelled says nothing: whoever cancelled it knows", () => {
    expect(failureText(new DOMException("aborted", "AbortError"))).toBeNull();
  });

  test("an error of the service says what the gateway said, and a 422 is put in words", () => {
    expect(failureText(new ApiError(404, "Unit 99999 not found."))).toBe("Unit 99999 not found.");
    expect(failureText(new ApiError(422, "The request has errors."))).toBe(
      "There is no data for that pollutant and year. Try another year.",
    );
    expect(failureText(new ApiError(0, "The service cannot be reached."))).toBe("The service cannot be reached.");
  });

  test.each([
    ["a TypeError of the code that read the answer", new TypeError("features is not iterable")],
    ["a RangeError", new RangeError("Invalid time value")],
    ["something that is not an error", "x is not iterable"],
    ["nothing", undefined],
  ])("%s does not show its message: it says things about the inside", (_name, error) => {
    expect(failureText(error)).toBe("The service is not available right now.");
  });
});
