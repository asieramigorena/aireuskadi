// The first view of the map: the whole Basque Country, whatever the size of the screen. The zoom
// is calculated from the size of the container, so that on a phone the country fits in its width
// and on a wide screen it is not lost in the middle.
import { WebMercatorViewport } from "@deck.gl/core";

export const MIN_ZOOM = 6.5; // further out the Basque Country is a dot
export const MAX_ZOOM = 14; // further in the simplified boundaries show their edges

// West, south, east, north of the Basque Autonomous Community.
const BOUNDS: [[number, number], [number, number]] = [
  [-3.45, 42.45],
  [-1.72, 43.47],
];

/** The view when the size of the container is not known yet (it has none until it is shown). */
export const DEFAULT_VIEW = {
  longitude: -2.65,
  latitude: 43.0,
  zoom: 8.5,
  minZoom: MIN_ZOOM,
  maxZoom: MAX_ZOOM,
  pitch: 40,
  bearing: 0,
};

export function fitView(width: number, height: number) {
  if (!(width > 0 && height > 0)) return DEFAULT_VIEW;
  // Room for the caption above, and a margin around: the map is tilted, so the country seems
  // shorter than it is and needs a little more air than a flat one.
  const margin = Math.round(Math.min(width, height) * 0.05);
  // The room for the caption cannot be more than a quarter of the height: in a container that is
  // smaller than the caption, the library refuses a padding bigger than the view.
  const top = Math.min(margin + 90, height * 0.25);
  const fitted = new WebMercatorViewport({ width, height }).fitBounds(BOUNDS, {
    padding: { top, bottom: margin, left: margin, right: margin },
  });
  return {
    ...DEFAULT_VIEW,
    longitude: fitted.longitude,
    latitude: fitted.latitude,
    // On a very small container the country would not fit even at the furthest zoom. There is no
    // upper limit to check: it would take a screen of tens of thousands of pixels to reach it.
    zoom: Math.max(fitted.zoom, MIN_ZOOM),
  };
}

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Inset {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** How much of the screen the panel covers, as margins of the map: with them the map is centred in
 * what is left, and the country is not hidden under the panel. The panel is a sheet from the
 * bottom on a narrow screen and a column on the side on a wide one. */
export function insetFor(panel: Box | null, width: number, height: number): Inset {
  const none = { top: 0, right: 0, bottom: 0, left: 0 };
  if (!panel || !(width > 0 && height > 0)) return none;
  const within = (value: number, max: number) => Math.min(Math.max(value, 0), max);
  if (panel.width >= width * 0.8) return { ...none, bottom: within(height - panel.top, height) };
  if (panel.left + panel.width / 2 > width / 2) {
    return { ...none, right: within(width - panel.left, width) };
  }
  return { ...none, left: within(panel.left + panel.width, width) };
}
