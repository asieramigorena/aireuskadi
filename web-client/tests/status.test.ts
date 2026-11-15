import { afterEach, describe, expect, test } from "vitest";
import { setLanguage, texts } from "../src/i18n";
import { createStatus } from "../src/status";

afterEach(() => setLanguage("en"));

describe("the status line", () => {
  test("says what it was told, in the language in use", () => {
    const line = document.createElement("p");
    const status = createStatus(line);

    status.say(() => texts().loadingMap);

    expect(line.textContent).toBe("Loading the map…");
  });

  test("says it again in the other language when only the language changes", () => {
    const line = document.createElement("p");
    const status = createStatus(line);
    status.say(() => texts().loadingMap);

    setLanguage("es");
    status.refresh();

    expect(line.textContent).toBe(texts().loadingMap);
    expect(line.textContent).not.toBe("Loading the map…");
  });

  test("says nothing again when it said nothing", () => {
    const line = document.createElement("p");
    const status = createStatus(line);
    status.say(() => texts().loadingMap);
    status.say(() => "");

    setLanguage("eu");
    status.refresh();

    expect(line.textContent).toBe("");
  });
});
