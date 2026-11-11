// The numbers of the panel, in English, with three significant figures: the declared amounts go
// from thousands of tonnes to a few grams.
import type { Selection } from "./router";
import type { StationReading } from "./types";

const number = (value: number) => value.toLocaleString("en-US", { maximumSignificantDigits: 3 });

const NO_DATA_TEXT = "No data";

export const formatTonnes = (value: number | null) =>
  value === null ? NO_DATA_TEXT : `${number(value)} t`;

export const formatDensity = (value: number | null) =>
  value === null ? NO_DATA_TEXT : `${number(value)} t/km²`;

export const formatRatio = (value: number | null) =>
  value === null ? NO_DATA_TEXT : `${number(value)}× the WHO guideline`;

export const formatArea = (value: number) => `${number(value)} km²`;

/** What the map shows. The API has no field for it: the label "declared industrial emissions" is
 * written here. */
export const mapCaption = (selection: Selection) =>
  `Declared industrial emissions of ${selection.pollutant} in ${selection.year}`;

/** The words for a call that failed. A 422 is a pollutant or a year without data: the gateway says
 * that the parameters are invalid, which tells a person nothing. */
export const errorText = (status: number, message: string) =>
  status === 422 ? "There is no data for that pollutant and year. Try another year." : message;

// --- the stations of a unit --------------------------------------------------------------------

/** A value with the unit that the station gave (the network writes it "µg/m3"). */
export const formatMeasure = (value: number, unit: string) => `${number(value)} ${unit.replace("/m3", "/m³")}`;

/** The time of a value, in UTC because that is what the API says and the station's own time zone is
 * not known here, whatever the time zone of the machine is. */
export const formatHour = (iso: string) =>
  `${new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "UTC",
  }).format(new Date(iso))} UTC`;

const AIR_POLLUTANTS: Record<string, string> = {
  NO2: "Nitrogen dioxide",
  PM25: "Particles PM2.5",
  PM10: "Particles PM10",
  O3: "Ozone",
  SO2: "Sulphur dioxide",
  CO: "Carbon monoxide",
};

/** The name of a pollutant that the stations measure; the API gives only its code. The ones of the
 * WHO are named here; for another, the name that the emissions of the same unit give it (`known`,
 * from the card) is used, and if there is none, the code. */
export const airPollutantName = (code: string, known?: ReadonlyMap<string, string>) =>
  AIR_POLLUTANTS[code] ?? known?.get(code) ?? code;

/** The comparison with the WHO guideline of a reading. A mean of a day with fewer than 24 values is
 * said to be partial: the API already refuses a ratio below 18. */
export function formatReadingRatio(reading: StationReading) {
  if (reading.who_period === null) return "No WHO guideline";
  if (reading.who_ratio === null) return "Not enough data";
  const partial = reading.who_period === "24h" && reading.who_samples !== null && reading.who_samples < 24;
  return partial ? `${formatRatio(reading.who_ratio)} (${reading.who_samples} of 24 hours)` : formatRatio(reading.who_ratio);
}
