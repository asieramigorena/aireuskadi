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

describe("the air quality in the panel", () => {
  test("the table of readings lets its text wrap: the panel hides what overflows, and a long note would be cut", () => {
    // `#panel td` does not wrap (the numbers of the emissions table stay in one line): this table
    // has text like "0.6× the WHO guideline (19 of 24 hours)", which has to.
    expect(css).toMatch(/\n#panel td \{\s*white-space:\s*nowrap/);
    expect(rule("#panel table.readings td")).toMatch(/white-space:\s*normal/);
  });

  test("a value and its unit stay in one line: '12' above 'µg/m³' reads as two things", () => {
    expect(rule("#panel .measure")).toMatch(/white-space:\s*nowrap/);
  });

  test("the name of a station can be long and does not push the panel sideways", () => {
    expect(rule("#panel summary")).toMatch(/overflow-wrap:\s*anywhere/);
  });

  test("the name of a pollutant that is a long word cannot push the table out of the panel", () => {
    expect(rule("#panel table.readings th")).toMatch(/overflow-wrap:\s*anywhere/);
  });

  test("on a finger, a station is as tall as the other targets: 44 px or more", () => {
    const coarse = css.slice(css.indexOf("@media (pointer: coarse)"));
    const block = coarse.slice(0, coarse.indexOf("\n}\n"));
    const summary = block.slice(block.indexOf("#panel summary"), block.indexOf("}", block.indexOf("#panel summary")));

    // 2 x 0.8rem of padding and a line of 1.4 are 47 px at 16 px: the same measure as the buttons.
    expect(summary).toMatch(/padding-block:\s*0\.8rem/);
  });

  test("the outline of the focus can be seen on the pale panel (the yellow one was made for the dark map)", () => {
    expect(rule("#panel :focus-visible")).toMatch(/outline-color:\s*var\(--ink\)/);
  });

  test("a station that is focused is not left under the header that stays at the top", () => {
    expect(rule("#panel")).toMatch(/scroll-padding-top:\s*[\d.]+rem/);
  });
});
