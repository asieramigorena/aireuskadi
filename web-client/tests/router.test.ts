import { afterEach, describe, expect, test, vi } from "vitest";
import { createRouter, homeUrl, parseLocation, unitUrl } from "../src/router";

describe("parseLocation", () => {
  test("the root is the map, with NOX and 2023 unless the URL says otherwise", () => {
    expect(parseLocation("/", "")).toEqual({
      route: { name: "home" },
      selection: { pollutant: "NOX", year: 2023 },
    });
  });

  test("/unit/:code is the panel of that unit", () => {
    expect(parseLocation("/unit/01036", "").route).toEqual({ name: "unit", code: "01036" });
    expect(parseLocation("/unit/9901", "").route).toEqual({ name: "unit", code: "9901" });
    expect(parseLocation("/unit/48", "").route).toEqual({ name: "unit", code: "48" });
  });

  test("the pollutant and the year come from the query", () => {
    expect(parseLocation("/", "?pollutant=CO&year=2019").selection).toEqual({
      pollutant: "CO",
      year: 2019,
    });
  });

  test.each([
    "?pollutant=nox",
    "?pollutant=NO%20X",
    "?pollutant=",
    "?pollutant=AAAAAAAAAAAAAAAAAAAAA",
    "?pollutant=<script>",
    "?pollutant=NOX'%3BDROP",
  ])("a pollutant that cannot be one (%s) is the default one", (query) => {
    expect(parseLocation("/", query).selection.pollutant).toBe("NOX");
  });

  test.each(["?year=abc", "?year=0", "?year=-5", "?year=2023.5", "?year=", "?year=1e3", "?year=99999999999999999999"])(
    "a year that cannot be one (%s) is the default one",
    (query) => {
      expect(parseLocation("/", query).selection.year).toBe(2023);
    },
  );

  test.each([
    "/unit",
    "/unit/",
    "/unit/1",
    "/unit/123",
    "/unit/123456",
    "/unit/0100a",
    "/unit/01036/extra",
    "/unit/..",
    "/unit/%2e%2e",
    "/units/01036",
    "/other",
  ])("a path that is not of the application (%s) is not found", (path) => {
    expect(parseLocation(path, "").route).toEqual({ name: "not-found" });
  });
});

describe("unitUrl", () => {
  test("is the path of the unit, and keeps the selection only when it is not the default", () => {
    expect(unitUrl("01036", { pollutant: "NOX", year: 2023 })).toBe("/unit/01036");
    expect(unitUrl("01036", { pollutant: "CO", year: 2019 })).toBe("/unit/01036?pollutant=CO&year=2019");
  });
});

describe("homeUrl", () => {
  test("is the root, and keeps the selection only when it is not the default", () => {
    expect(homeUrl({ pollutant: "NOX", year: 2023 })).toBe("/");
    expect(homeUrl({ pollutant: "CO", year: 2019 })).toBe("/?pollutant=CO&year=2019");
    expect(homeUrl({ pollutant: "NOX", year: 2020 })).toBe("/?year=2020");
  });
});

describe("createRouter", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  test("tells the state of the URL when it starts", () => {
    window.history.replaceState(null, "", "/unit/01036?pollutant=CO");
    const onChange = vi.fn();

    createRouter(window, onChange).start();

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual({
      route: { name: "unit", code: "01036" },
      selection: { pollutant: "CO", year: 2023 },
    });
  });

  test("navigating changes the URL, adds a step to the history and tells the new state", () => {
    const onChange = vi.fn();
    const router = createRouter(window, onChange);
    router.start();
    const steps = window.history.length;

    router.navigate("/unit/48");

    expect(window.location.pathname).toBe("/unit/48");
    expect(window.history.length).toBe(steps + 1);
    expect(onChange.mock.calls.at(-1)?.[0].route).toEqual({ name: "unit", code: "48" });
  });

  test("Back goes to the previous state and tells it", async () => {
    const onChange = vi.fn();
    const router = createRouter(window, onChange);
    router.start();
    router.navigate("/unit/48");

    window.history.back();
    await vi.waitFor(() => expect(window.location.pathname).toBe("/"));

    expect(onChange.mock.calls.at(-1)?.[0].route).toEqual({ name: "home" });
  });

  test("navigating to the place where it already is does not add a step", () => {
    const router = createRouter(window, vi.fn());
    router.start();
    router.navigate("/unit/48");
    const steps = window.history.length;

    router.navigate("/unit/48");

    expect(window.history.length).toBe(steps);
  });
});
