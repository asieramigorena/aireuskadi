// What the page says with numbers and names, in the language in use (src/i18n). The numbers have
// three significant figures: the declared amounts go from thousands of tonnes to a few grams.
import { texts } from "./i18n";
import type { Selection, View } from "./router";
import type { StationReading } from "./types";

/** A number with three significant figures, written as the language writes it. The digits come from
 * `Intl` in English (every browser has it) and the separators from the dictionary: asking the browser
 * for Basque gives "0.6" and "M11" in some of them. */
function number(value: number): string {
  const words = texts();
  const plain = value.toLocaleString("en-US", { maximumSignificantDigits: 3, useGrouping: false });
  const [whole, fraction] = plain.split(".");
  const grouped =
    whole.replace("-", "").length >= words.groupFrom
      ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, words.groupSeparator)
      : whole;
  return fraction === undefined ? grouped : `${grouped}${words.decimalSeparator}${fraction}`;
}

export const formatTonnes = (value: number | null) => (value === null ? texts().noData : `${number(value)} t`);

export const formatDensity = (value: number | null) => (value === null ? texts().noData : `${number(value)} t/km²`);

export const formatRatio = (value: number | null) =>
  value === null ? texts().noData : texts().ratioOfGuideline(number(value));

export const formatArea = (value: number) => `${number(value)} km²`;

/** A name in the middle of a sentence: "nitrogen dioxide", but the name of a formula ("PM2.5
 * particles", "H2S") is left as it is. */
function lowerFirst(name: string): string {
  const second = name.charAt(1);
  return second !== "" && second === second.toLowerCase() && second !== second.toUpperCase()
    ? name.charAt(0).toLowerCase() + name.slice(1)
    : name;
}

/** What the map shows. The API has no field for it: the label is written here. */
export function mapCaption(selection: Selection): string {
  if (selection.view === "emissions") return texts().captionEmissions(selection.pollutant, selection.year);
  // A code that has no name ("H2S") is left as it is.
  const name = airPollutantName(selection.pollutant);
  return texts().captionAir(name === selection.pollutant ? name : lowerFirst(name));
}

/** What the map is, for whoever cannot see it. */
export const mapLabel = (view: View) => (view === "emissions" ? texts().mapLabelEmissions : texts().mapLabelAir);

/** The words for a call that failed, by its code: what the service says is not shown (it is in
 * English, and a message that is not ours can say things about the inside). A 422 is a pollutant or a
 * year without data: the gateway says that the parameters are invalid, which tells a person nothing. */
export function errorText(status: number): string {
  if (status === 422) return texts().noDataForSelection;
  if (status === 404) return texts().notFound;
  if (status === 0) return texts().serviceUnreachable;
  return texts().serviceUnavailable;
}

// --- the stations of a unit --------------------------------------------------------------------

/** A value with the unit that the station gave (the network writes it "µg/m3"). */
export const formatMeasure = (value: number, unit: string) => `${number(value)} ${unit.replace("/m3", "/m³")}`;

/** The time of a value, in UTC because that is what the API says and the station's own time zone is
 * not known here, whatever the time zone of the machine is. The months and the order of the pieces
 * come from the dictionary: nothing is asked of the browser for a language. A time that is not one
 * throws, as it always did: the section of the panel that shows it says that it is not available. */
export function formatHour(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) throw new RangeError("Invalid time value");
  const two = (value: number) => String(value).padStart(2, "0");
  const time = `${two(date.getUTCHours())}:${two(date.getUTCMinutes())}`;
  return texts().hour(String(date.getUTCDate()), texts().months[date.getUTCMonth()], time);
}

/** The pollutants that the map of the air quality offers: the ones that have a WHO guideline. */
export const AIR_POLLUTANT_CODES = ["NO2", "PM25", "PM10", "O3", "SO2", "CO"];

// An own property only: a code like "toString" has no name, it is not a function of the table.
const named = (table: Record<string, string>, code: string): string | undefined =>
  Object.hasOwn(table, code) ? table[code] : undefined;

/** The name of a pollutant that the stations measure; the API gives only its code. The ones of the
 * WHO are named by the dictionary; for another, the name that the emissions of the same unit give it
 * (`known`, from the card) is used, and if there is none, the code. */
export const airPollutantName = (code: string, known?: ReadonlyMap<string, string>) =>
  named(texts().airPollutants, code) ?? known?.get(code) ?? code;

/** The name of a pollutant of the emissions: the one of the language, and where it has none (English
 * has none: the API speaks English) the one that the API gives. */
export const emissionName = (code: string, apiName: string) => named(texts().pollutants, code) ?? apiName;

/** The comparison with the WHO guideline of a reading. A mean of a day with fewer than 24 values is
 * said to be partial: the API already refuses a ratio below 18. */
export function formatReadingRatio(reading: StationReading) {
  if (reading.who_period === null) return texts().noGuideline;
  if (reading.who_ratio === null) return texts().notEnoughData;
  const partial = reading.who_period === "24h" && reading.who_samples !== null && reading.who_samples < 24;
  const ratio = formatRatio(reading.who_ratio);
  return partial ? `${ratio} (${texts().partialDay(reading.who_samples as number)})` : ratio;
}
