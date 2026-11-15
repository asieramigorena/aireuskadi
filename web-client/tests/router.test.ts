import { afterEach, describe, expect, test, vi } from "vitest";
import { createRouter, homeUrl, parseLocation, unitUrl, type Selection } from "../src/router";

const emissions = (pollutant: string, year: number): Selection => ({ view: "emissions", pollutant, year });
const air = (pollutant: string): Selection => ({ view: "air", pollutant, year: 2023 });

describe("parseLocation", () => {
  test("the root is the map, with NOX and 2023 unless the URL says otherwise", () => {
    expect(parseLocation("/", "")).toEqual({
      route: { name: "home" },
      selection: { view: "emissions", pollutant: "NOX", year: 2023 },
    });
  });

  test("/unit/:code is the panel of that unit", () => {
    expect(parseLocation("/unit/01036", "").route).toEqual({ name: "unit", code: "01036", station: null });
    expect(parseLocation("/unit/9901", "").route).toEqual({ name: "unit", code: "9901", station: null });
    expect(parseLocation("/unit/48", "").route).toEqual({ name: "unit", code: "48", station: null });
  });

  test("the pollutant and the year come from the query", () => {
    expect(parseLocation("/", "?pollutant=CO&year=2019").selection).toEqual(emissions("CO", 2019));
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
    expect(unitUrl("01036", emissions("NOX", 2023))).toBe("/unit/01036");
    expect(unitUrl("01036", emissions("CO", 2019))).toBe("/unit/01036?pollutant=CO&year=2019");
  });
});

describe("homeUrl", () => {
  test("is the root, and keeps the selection only when it is not the default", () => {
    expect(homeUrl(emissions("NOX", 2023))).toBe("/");
    expect(homeUrl(emissions("CO", 2019))).toBe("/?pollutant=CO&year=2019");
    expect(homeUrl(emissions("NOX", 2020))).toBe("/?year=2020");
  });
});

describe("the language that the person chose", () => {
  test("is in the address, and only when it was chosen: without it the browser decides", () => {
    expect(parseLocation("/", "").selection).not.toHaveProperty("lang");
    expect(parseLocation("/", "?lang=eu").selection.lang).toBe("eu");
    expect(parseLocation("/", "?lang=es").selection.lang).toBe("es");
    expect(parseLocation("/", "?lang=en").selection.lang).toBe("en");
  });

  test.each(["?lang=", "?lang=fr", "?lang=EU", "?lang=eu-ES", "?lang=<script>", "?lang=eu%20", "?lang=%00"])(
    "a language that the page does not have (%s) is as if there were none",
    (query) => {
      expect(parseLocation("/", query).selection).not.toHaveProperty("lang");
    },
  );

  test("travels in every address that the page makes, next to the rest of the choice", () => {
    expect(homeUrl({ ...emissions("NOX", 2023), lang: "es" })).toBe("/?lang=es");
    expect(homeUrl({ ...air("NO2"), lang: "eu" })).toBe("/?view=air&lang=eu");
    expect(homeUrl({ ...emissions("CO", 2019), lang: "en" })).toBe("/?pollutant=CO&year=2019&lang=en");
    expect(unitUrl("48020", { ...air("O3"), lang: "es" }, 195)).toBe("/unit/48020?view=air&pollutant=O3&lang=es&station=195");
  });

  test("no choice (nothing, or null) leaves the address as it was", () => {
    expect(homeUrl({ ...emissions("NOX", 2023), lang: null })).toBe("/");
    expect(unitUrl("48020", { ...air("NO2"), lang: null })).toBe("/unit/48020?view=air");
  });

  test("what the address says is what is read back", () => {
    const chosen: Selection = { ...air("PM10"), lang: "eu" };

    expect(parseLocation("/", homeUrl(chosen).slice(1)).selection).toEqual(chosen);
    expect(parseLocation("/unit/48020", unitUrl("48020", chosen, 7).split("?")[1].replace(/^/, "?")).selection).toEqual(chosen);
  });

  test("the language is read on the address of a unit as it is on the home, and does not touch the rest", () => {
    expect(parseLocation("/unit/48020", "?lang=es&station=7").route).toEqual({ name: "unit", code: "48020", station: 7 });
    expect(parseLocation("/unit/48020", "?lang=es").selection.lang).toBe("es");
  });
});

describe("the station that is open in the panel", () => {
  test("the unit says which station of it is open, by its id", () => {
    expect(parseLocation("/unit/48020", "?view=air&station=212")).toEqual({
      route: { name: "unit", code: "48020", station: 212 },
      selection: air("NO2"),
    });
  });

  test.each(["?station=", "?station=abc", "?station=0", "?station=-3", "?station=1.5", "?station=0212", "?station=1e3", "?station=%EF%BC%91", "?station=12345678901", "?station=212%0A"])(
    "a station that cannot be one (%s) is no station",
    (query) => {
      expect((parseLocation("/unit/48020", query).route as { station: number | null }).station).toBeNull();
    },
  );

  test("the biggest id that can be one is ten digits", () => {
    expect((parseLocation("/unit/48020", "?station=9999999999").route as { station: number }).station).toBe(9999999999);
  });

  test("the home has no station, and the address of a unit keeps it only in the map of the air quality", () => {
    expect(parseLocation("/", "?view=air&station=212").route).toEqual({ name: "home" });
    expect(unitUrl("48020", air("NO2"), 212)).toBe("/unit/48020?view=air&station=212");
    expect(unitUrl("48020", air("O3"), 212)).toBe("/unit/48020?view=air&pollutant=O3&station=212");
    expect(unitUrl("48020", emissions("NOX", 2023), 212)).toBe("/unit/48020");
    expect(unitUrl("48020", air("NO2"))).toBe("/unit/48020?view=air");
  });

  test("what the address says is what is read back", () => {
    const state = parseLocation("/unit/48020", unitUrl("48020", air("PM10"), 7).split("?")[1].replace(/^/, "?"));

    expect(state).toEqual({ route: { name: "unit", code: "48020", station: 7 }, selection: air("PM10") });
  });
});

describe("the view of the map", () => {
  test("the map of emissions is the default one, and the URL only says `air` for the other", () => {
    expect(parseLocation("/", "").selection.view).toBe("emissions");
    expect(parseLocation("/", "?view=emissions").selection.view).toBe("emissions");
    expect(parseLocation("/", "?view=air").selection.view).toBe("air");
  });

  test.each(["?view=", "?view=AIR", "?view=air%20", "?view=<script>", "?view=maps", "?view=air&view=emissions"])(
    "a view that is not one (%s) is the default one",
    (query) => {
      // The first value is the one that is read: `air&view=emissions` is `air`, the rest are not views.
      const expected = query === "?view=air&view=emissions" ? "air" : "emissions";
      expect(parseLocation("/", query).selection.view).toBe(expected);
    },
  );

  test("each view has its own pollutant by default: NOX for the emissions and NO2 for the air", () => {
    expect(parseLocation("/", "").selection.pollutant).toBe("NOX");
    expect(parseLocation("/", "?view=air").selection.pollutant).toBe("NO2");
    expect(parseLocation("/", "?view=air&pollutant=PM10").selection.pollutant).toBe("PM10");
    expect(parseLocation("/", "?view=air&pollutant=nox").selection.pollutant).toBe("NO2");
  });

  test("the unit panel keeps the view, so a link shows the map that the person saw", () => {
    expect(parseLocation("/unit/48020", "?view=air&pollutant=O3")).toEqual({
      route: { name: "unit", code: "48020", station: null },
      selection: air("O3"),
    });
  });

  test("the air has no year: it is the latest value, so the URL does not carry one", () => {
    expect(homeUrl(air("NO2"))).toBe("/?view=air");
    expect(homeUrl(air("PM10"))).toBe("/?view=air&pollutant=PM10");
    expect(unitUrl("48020", air("O3"))).toBe("/unit/48020?view=air&pollutant=O3");
    expect(homeUrl({ view: "air", pollutant: "NO2", year: 2019 })).toBe("/?view=air");
  });

  test("what the URL says is what is read back, for both views", () => {
    for (const selection of [emissions("CO", 2019), emissions("NOX", 2023), air("NO2"), air("SO2")]) {
      expect(parseLocation("/", homeUrl(selection).slice(1)).selection).toEqual(selection);
    }
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
      route: { name: "unit", code: "01036", station: null },
      selection: emissions("CO", 2023),
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
    expect(onChange.mock.calls.at(-1)?.[0].route).toEqual({ name: "unit", code: "48", station: null });
  });

  test.each([
    ["another site", "https://evil.example/unit/48020"],
    ["another site with the scheme of the page", "//evil.example/unit/48020"],
    ["a script", "javascript:alert(1)"],
    ["a path that climbs", "/unit/../health"],
    ["a unit that is not one", "/unit/12abc"],
    ["a path of nothing", "/other"],
    ["a unit with a path after it", "/unit/48020/extra"],
  ])("an address that is not one of the application (%s) is not followed: the page stays where it is", (_name, url) => {
    const onChange = vi.fn();
    const router = createRouter(window, onChange);
    router.start();
    const steps = window.history.length;
    const before = window.location.href;
    onChange.mockClear();

    router.navigate(url);

    expect(window.location.href).toBe(before);
    expect(window.history.length).toBe(steps);
    expect(onChange).not.toHaveBeenCalled();
  });

  test("the addresses that the application builds are followed, with their query", () => {
    const onChange = vi.fn();
    const router = createRouter(window, onChange);
    router.start();

    router.navigate("/unit/48020?view=air&pollutant=O3&station=195");

    expect(window.location.pathname + window.location.search).toBe("/unit/48020?view=air&pollutant=O3&station=195");
    expect(onChange.mock.calls.at(-1)?.[0]).toEqual({
      route: { name: "unit", code: "48020", station: 195 },
      selection: { view: "air", pollutant: "O3", year: 2023 },
    });
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
