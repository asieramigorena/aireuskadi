// Which units are drawn at each zoom: the further away, the bigger the unit. The limits were chosen
// by eye: the first view (view.ts) fits the whole Basque Country in the screen, and on a laptop
// or a bigger screen that is drawn by municipality; on a phone, where it has to be further away, it
// is drawn by district or territory. Going out it is district and then territory.
import type { Level } from "./types";

const DISTRICTS_BELOW = 8.2;
const TERRITORIES_BELOW = 7.6;

export function levelForZoom(zoom: number): Level {
  // A zoom that is not a number fails both comparisons and gets the most detailed level, which is
  // the one that always exists.
  if (zoom < TERRITORIES_BELOW) return "territory";
  if (zoom < DISTRICTS_BELOW) return "district";
  return "municipality";
}
