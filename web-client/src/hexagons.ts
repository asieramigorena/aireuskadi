// The size of the hexagons follows the zoom. A hexagon of a fixed size in metres is a small mark
// when the whole country is in view, but when the map is close it covers several municipalities
// and ignores their borders, and its column hides the ones behind it. So the radius is chosen so
// that a hexagon is about the same size on the screen at any zoom: the points are grouped when
// they are far away and separate when the map is close, where a hexagon fits inside a municipality.

export const HEXAGON_MAX_RADIUS = 1500; // metres: what it always was, for the whole country
export const HEXAGON_MIN_RADIUS = 100; // a facility is not a mark of a few metres

// What the radius should measure on the screen, in pixels: the size that the hexagons had at the
// first view of a laptop, big enough to be seen and to be told apart from each other.
const RADIUS_PIXELS = 14;
// The circumference of the Earth, and the latitude of the middle of the Basque Country: a pixel is
// not the same number of metres at every latitude on this map.
const EARTH_METRES = 40_075_016.686;
const LATITUDE = 43;
// The tiles of the map are 512 pixels wide at zoom 0.
const TILE = 512;

/** The radius of the hexagons for a zoom, in metres. It changes in steps of a square root of 2
 * (two steps per zoom level): the points are grouped again only when the step changes, not at
 * every turn of the wheel. */
export function hexRadiusForZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) return HEXAGON_MAX_RADIUS;
  const metresPerPixel = (EARTH_METRES * Math.cos((LATITUDE * Math.PI) / 180)) / (TILE * 2 ** zoom);
  const wanted = metresPerPixel * RADIUS_PIXELS;
  const steps = Math.max(0, Math.round(2 * Math.log2(HEXAGON_MAX_RADIUS / wanted)));
  return Math.max(HEXAGON_MIN_RADIUS, HEXAGON_MAX_RADIUS / 2 ** (steps / 2));
}
