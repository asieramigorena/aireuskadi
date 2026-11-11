import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

// The layout is checked in a browser (see the notes of the project); happy-dom has no layout. What
// can be pinned here is the rule that keeps the name of the unit and the button to close in view.

// The tests run from the folder of web-client (npm test).
const css = readFileSync(join(process.cwd(), "styles/style.css"), "utf8");

/** The declarations of the first rule with this exact selector. */
function rule(selector: string): string {
  const start = css.indexOf(`\n${selector} {`);
  expect(start, `no rule for ${selector}`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf("}", start));
}

describe("the panel of a unit", () => {
  test("its header, with the name and the button to close, stays at the top while the table is scrolled", () => {
    const header = rule("#panel header");

    expect(header).toMatch(/position:\s*sticky/);
    expect(header).toMatch(/top:\s*0\s*;/);
    // Opaque: the rows that go under it must not show through.
    expect(header).toMatch(/background:\s*var\(--paper\)/);
    // It carries the space that the panel does not have on top, from a variable that exists.
    expect(header).toMatch(/padding:\s*var\(--panel-pad-top\)/);
    expect(rule("#panel")).toMatch(/--panel-pad-top:\s*[\d.]+rem/);
  });

  test("the panel has no padding on top: it would be a strip above the header where the rows show", () => {
    expect(rule("#panel")).toMatch(/padding:\s*0\s/);
  });

  test("on a narrow screen (the sheet of a phone) the panel has no padding on top either", () => {
    const narrow = css.slice(css.indexOf("@media (max-width: 52rem)"));
    const sheet = narrow.slice(narrow.indexOf("  #panel {"), narrow.indexOf("}", narrow.indexOf("  #panel {")));

    expect(sheet).toMatch(/padding:\s*0\s/);
  });
});
