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

describe("the controls to choose the map", () => {
  test("can be clicked: the caption around them lets the pointer through to the map, and they do not", () => {
    expect(rule(".caption")).toMatch(/pointer-events:\s*none/);
    expect(rule(".controls")).toMatch(/pointer-events:\s*auto/);
  });

  test("the map that is shown is not only another colour: it is bold and filled, so it is seen without colour", () => {
    const active = rule('.controls a[aria-current="true"]');

    expect(active).toMatch(/background:/);
    expect(active).toMatch(/font-weight:\s*[6-9][0-9]0/);
  });

  test("on a finger, the links and the selector are 44 px or more", () => {
    const coarse = css.slice(css.indexOf("@media (pointer: coarse)"));
    const block = coarse.slice(0, coarse.indexOf("\n}\n"));
    const controls = block.slice(block.indexOf(".controls a"), block.indexOf("}", block.indexOf(".controls a")));

    expect(controls).toMatch(/\.controls select/);
    expect(controls).toMatch(/min-height:\s*2\.75rem/);
  });
});

/** The text of a block of the sheet that starts at `start` (a media query) and ends at its closing. */
function mediaBlock(start: string): string {
  const from = css.slice(css.indexOf(start));
  return from.slice(0, from.indexOf("\n}\n"));
}

/** The rems that a rule of `block` adds to `--bottom` or to the safe area ("bottom: calc(... + 3.4rem)"). */
function lifted(block: string, selector: string): number {
  const at = block.indexOf(`\n  ${selector} {`);
  expect(at, `no rule for ${selector} in the block`).toBeGreaterThanOrEqual(0);
  const text = block.slice(at, block.indexOf("}", at));
  const match = /\+\s*([\d.]+)rem/.exec(text);
  expect(match, `${selector} does not lift`).not.toBeNull();
  return Number(match![1]);
}

describe("the map of the air quality on a phone: its credits are longer, so what is above them goes higher", () => {
  test("the legend and the sheet of the panel are higher than in the emissions", () => {
    const narrow = mediaBlock("@media (max-width: 52rem)");

    expect(lifted(narrow, ".air-view .legend")).toBeGreaterThan(lifted(narrow, ".legend"));
    expect(lifted(narrow, ".air-view #panel")).toBeGreaterThan(lifted(narrow, "#panel"));
  });

  test("on a phone on its side the panel is at the side and does not float: the later block undoes the lift of the sheet", () => {
    const short = mediaBlock("@media (max-height: 30rem)");
    const at = short.indexOf(".air-view #panel {");

    expect(at, "no .air-view #panel in the block of the phone on its side").toBeGreaterThanOrEqual(0);
    expect(short.slice(at, short.indexOf("}", at))).toMatch(/bottom:\s*var\(--bottom\)/);
  });
});

describe("the legend of the air quality", () => {
  test("the mark of the guideline is in the middle of the bar, which goes from 0 to twice the guideline, and has an edge to be seen on the yellow", () => {
    expect(rule(".legend-tick")).toMatch(/left:\s*50%/);
    expect(rule(".legend-tick")).toMatch(/box-shadow:/);
    expect(rule("#legend-bar")).toMatch(/position:\s*relative/);
  });

  test("the three labels keep the one of the middle in the middle, whatever the width of the other two", () => {
    expect(rule(".legend-ends.three")).toMatch(/grid-template-columns:\s*1fr auto 1fr/);
  });

  test("a label is one line, and on a phone on its side the legend of this map is wide enough for the three", () => {
    expect(rule(".legend-ends.three span")).toMatch(/white-space:\s*nowrap/);
    const short = css.slice(css.indexOf("@media (max-height: 30rem)"));
    expect(short.slice(0, short.indexOf("\n}\n"))).toMatch(/\.air-view \.legend \{[^}]*width:\s*12rem/);
  });
});

describe("the ratio of the emissions", () => {
  test("wraps, or a long phrase (Basque) pushes the table out of the panel, which hides what overflows", () => {
    expect(rule("#panel td.ratio")).toMatch(/white-space:\s*normal/);
  });
});

describe("the selector of the language", () => {
  test("can be clicked: the caption around it lets the pointer through to the map, and it does not", () => {
    expect(rule(".languages")).toMatch(/pointer-events:\s*auto/);
  });

  test("the language in use is filled and bold, so it is seen without the colour", () => {
    const current = rule('.languages a[aria-current="true"]');

    expect(current).toMatch(/background:/);
    expect(current).toMatch(/font-weight:\s*[6-9][0-9]0/);
  });

  test("sits next to the name of the page, on one line that wraps when the screen is narrow", () => {
    expect(rule(".brand")).toMatch(/display:\s*flex/);
    expect(rule(".brand")).toMatch(/flex-wrap:\s*wrap/);
  });

  test("with a pointer, each language is at least 24 px high, as a target needs", () => {
    expect(rule(".languages a")).toMatch(/min-height:\s*1\.5rem/);
  });

  test("on a finger, each language is 44 px or more on both sides", () => {
    const coarse = css.slice(css.indexOf("@media (pointer: coarse)"));
    const block = coarse.slice(0, coarse.indexOf("\n}\n"));
    const languages = block.slice(block.indexOf(".languages a"), block.indexOf("}", block.indexOf(".languages a")));

    expect(languages).toMatch(/min-height:\s*2\.75rem/);
    expect(languages).toMatch(/min-width:\s*2\.75rem/);
  });
});
