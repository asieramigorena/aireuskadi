import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "../src/api";
import { renderAsk, questionsOf, type AskFn, type ModelsFn } from "../src/ask";
import { setLanguage, texts } from "../src/i18n";
import type { UnitCard } from "../src/types";

const CARD: UnitCard = {
  code: "48020",
  level: "municipality",
  name: "Bilbao",
  area_km2: 40.6,
  district: null,
  territory: null,
  emissions: [
    { year: 2023, pollutant: "NOX", name: "Nitrogen oxides", declared_t: 250, t_km2: 6.7, who_ratio: null },
    { year: 2023, pollutant: "CO2", name: "Carbon dioxide", declared_t: 900, t_km2: 22, who_ratio: null },
    { year: 2022, pollutant: "SO2", name: "Sulphur oxides", declared_t: 9, t_km2: 0.2, who_ratio: null },
  ],
  air_quality: {
    attribution: "x",
    measured: true,
    reason: null,
    stations: [
      {
        id: 7, code: "BI1", name: "Mazarredo", geometry: null, meteo_only: false, recent: true,
        readings: ["NO2", "NOX"].map((pollutant) => ({
          pollutant, ts: "2026-11-25T08:00:00Z", value: 19, unit: "µg/m3", who_period: "24h" as const,
          who_guideline_ugm3: 25, who_mean_ugm3: 15, who_samples: 24, who_ratio: 0.6,
        })),
      },
    ],
  },
};

afterEach(() => setLanguage("en"));

const LOGGED_IN = "user1";
const SELECTION = { view: "emissions" as const, pollutant: "NOX", year: 2023 };

/** The box of the questions, drawn in a new element: about CARD (or no unit), logged in or not. */
function box(
  ask: AskFn,
  account: string | null = LOGGED_IN,
  card: UnitCard | null = CARD,
  models: ModelsFn = async () => ["openai/gpt-oss-120b", "openai/gpt-oss-20b"],
): HTMLElement {
  const root = document.createElement("section");
  renderAsk(root, card, SELECTION, ask, account, models);
  return root;
}
type Asked = { question: string; llm: { provider: string; model: string; key: string } };

/** Types the key, chooses the question, presses the button and waits for the answer. */
async function askWith(answer: () => Promise<{ text: string; model: string }>, question = "summary") {
  const asked: Asked[] = [];
  const section = box(async (q, llm) => {
    asked.push({ question: q, llm });
    return answer();
  });
  const key = section.querySelector<HTMLInputElement>("input[type=password]")!;
  key.value = "gsk-secret-1";
  key.dispatchEvent(new Event("input"));
  key.dispatchEvent(new Event("change"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  section.querySelector<HTMLSelectElement>("select.question")!.value = question;
  section.querySelector("button")!.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { section, asked };
}

describe("the questions about a unit", () => {
  test("are the two of the unit, the two general ones, and one per pollutant of its stations or of the map", () => {
    // A big municipality declares 30 or 40 pollutants: only the one of the map is offered (NOX, also
    // measured), not CO2. NO2 and NOX are measured by its station.
    expect(questionsOf(CARD, 2023, "NOX").map((question) => question.key)).toEqual([
      "summary",
      "meaning",
      "who_ratio",
      "density",
      "pollutant:NO2",
      "pollutant:NOX",
    ]);
  });

  test("without a unit the general ones can be asked, and the ones about a unit wait for one", () => {
    const questions = questionsOf(null, 2023, "NOX");
    expect(questions.map((question) => [question.key, question.needsUnit])).toEqual([
      ["summary", true],
      ["meaning", true],
      ["who_ratio", false],
      ["density", false],
      ["pollutant:NOX", false],
    ]);

    const options = [...box(async () => ({ text: "", model: "" }), LOGGED_IN, null).querySelectorAll("option")];
    const summary = options.find((option) => option.value === "summary")!;
    expect(summary.disabled).toBe(true);
    expect(summary.classList.contains("needs-unit")).toBe(true);
    expect(options.find((option) => option.value === "who_ratio")!.disabled).toBe(false);
  });

  test("with a unit open every question can be asked", () => {
    const options = [...box(async () => ({ text: "", model: "" })).querySelectorAll("select.question option")];

    expect(options.every((option) => !(option as HTMLOptionElement).disabled)).toBe(true);
  });

  test("someone who is not logged in is asked to log in or sign up, and has no field for a key", () => {
    const section = box(async () => ({ text: "", model: "" }), null);

    const links = [...section.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(links).toEqual(["/user?lang=en", "/user/signup?lang=en"]);
    expect(section.querySelector("input[type=password]")).toBeNull();
  });

  test("the provider, the model and the key go with the question; a provider fills its model", async () => {
    const { section, asked } = await askWith(async () => ({ text: "x", model: "m" }));
    expect(asked[0]).toEqual({
      question: "summary",
      llm: { provider: "groq", model: "openai/gpt-oss-120b", key: "gsk-secret-1" },
    });

    const provider = section.querySelector<HTMLSelectElement>("select.provider")!;
    provider.value = "mistral";
    provider.dispatchEvent(new Event("change"));
    expect(section.querySelector<HTMLSelectElement>("select.model")!.value).toBe("mistral-small-latest");
  });

  test("the key stays only in the memory of the page", async () => {
    await askWith(async () => ({ text: "x", model: "m" }));

    for (const storage of [localStorage, sessionStorage]) {
      expect(JSON.stringify({ ...storage })).not.toContain("gsk-secret-1");
    }
    expect(document.cookie).not.toContain("gsk-secret-1");
  });

  test("the answer is written as text, with the note that a model wrote it", async () => {
    const { section } = await askWith(async () => ({ text: "<b>x</b>", model: "m" }));

    expect(section.querySelector(".answer")!.textContent).toBe("<b>x</b>");
    expect(section.querySelector("b")).toBeNull();
    expect(section.textContent).toContain(texts().generatedNote);
  });

  test.each([
    [429, () => texts().askTooMany],
    [503, () => texts().askNotAvailable],
    [403, () => texts().askKeyRefused],
  ])("a %i says why in words", async (status, words) => {
    const { section } = await askWith(async () => { throw new ApiError(status); });

    expect(section.querySelector("[role=status]")!.textContent).toBe(words());
  });

  test("a 401 (the session ended) says so with the two ways in", async () => {
    const { section } = await askWith(async () => { throw new ApiError(401); });

    const status = section.querySelector("[role=status]")!;
    expect(status.textContent).toContain(texts().askLogIn);
    expect([...status.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "/user?lang=en",
      "/user/signup?lang=en",
    ]);
  });

  test("without a key nothing is sent and the key is asked for", async () => {
    const asked: string[] = [];
    const section = box(async (q) => {
      asked.push(q);
      return { text: "x", model: "m" };
    });
    const key = section.querySelector<HTMLInputElement>("input[type=password]")!;
    key.value = "";
    key.dispatchEvent(new Event("input"));

    section.querySelector("button")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(asked).toEqual([]);
    expect(section.querySelector("[role=status]")!.textContent).toBe(texts().askNeedKey);
  });
});


describe("the models of the provider", () => {
  test("come from the provider with the key, and the one chosen is the one asked", async () => {
    vi.useFakeTimers();
    const asked: Asked[] = [];
    const listed: string[][] = [];
    const section = box(
      async (q, llm) => {
        asked.push({ question: q, llm });
        return { text: "x", model: "m" };
      },
      LOGGED_IN,
      CARD,
      async (provider, key) => {
        listed.push([provider, key]);
        return ["openai/gpt-oss-120b", "qwen/qwen3-32b"];
      },
    );
    const key = section.querySelector<HTMLInputElement>("input[type=password]")!;
    key.value = "gsk-secret-1";
    key.dispatchEvent(new Event("input"));
    await vi.advanceTimersByTimeAsync(1000);
    vi.useRealTimers();

    const model = section.querySelector<HTMLSelectElement>("select.model")!;
    expect([...model.options].map((option) => option.value)).toEqual(["openai/gpt-oss-120b", "qwen/qwen3-32b"]);
    model.value = "qwen/qwen3-32b";
    model.dispatchEvent(new Event("change"));
    section.querySelector("button")!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    // The provider chosen in the page (the choice stays in the memory of the page, like in a tab).
    const provider = section.querySelector<HTMLSelectElement>("select.provider")!.value;
    expect(listed.at(-1)).toEqual([provider, "gsk-secret-1"]);
    expect(asked[0].llm.model).toBe("qwen/qwen3-32b");
  });
});


describe("when the models are asked", () => {
  test("a moment after the key is typed, without leaving the field", async () => {
    vi.useFakeTimers();
    const listed: string[] = [];
    const section = box(async () => ({ text: "x", model: "m" }), LOGGED_IN, CARD, async (_provider, key) => {
      listed.push(key);
      return ["a-model"];
    });
    const key = section.querySelector<HTMLInputElement>("input[type=password]")!;
    key.value = "gsk-other-2";
    key.dispatchEvent(new Event("input"));

    await vi.advanceTimersByTimeAsync(1000);
    vi.useRealTimers();

    expect(listed.at(-1)).toBe("gsk-other-2");
  });
});
