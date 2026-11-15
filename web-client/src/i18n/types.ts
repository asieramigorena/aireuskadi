// The texts of the page. Every language is one dictionary with this shape, so a text that is missing
// in a language is an error of the compiler, and not a hole that someone finds in the browser.

export type Language = "eu" | "es" | "en";

/** The pollutants that the stations measure and that have a WHO guideline. */
export type AirCode = "NO2" | "PM25" | "PM10" | "O3" | "SO2" | "CO";

export interface Texts {
  // How the numbers and the dates are written. The dictionary says it and the browser is not asked:
  // the data of a language can be missing from a browser (the Chromium of a Linux distribution writes
  // November as "M11" and a decimal as "0.6" in Basque), and the page would then be half in Basque.
  decimalSeparator: string;
  groupSeparator: string;
  /** The number of digits of the whole part from which the thousands are grouped. */
  groupFrom: number;
  /** The twelve months, short, from January. */
  months: readonly string[];
  /** The name of the language, in that language (it is the title of its link in the selector). */
  languageName: string;

  // The page.
  mapChoiceLabel: string;
  languageChoiceLabel: string;
  panelLabel: string;
  emissionsCredit: string;
  airCredit: (attribution: string) => string;
  loadingMap: string;
  pageNotFound: string;

  // What is said when a call fails.
  serviceUnreachable: string;
  serviceUnavailable: string;
  notFound: string;
  noDataForSelection: string;

  // The two maps and their controls.
  viewEmissions: string;
  viewAir: string;
  airPollutantLabel: string;
  mapLabelEmissions: string;
  mapLabelAir: string;
  captionEmissions: (pollutant: string, year: number) => string;
  captionAir: (pollutant: string) => string;

  // The numbers.
  noData: string;
  ratioOfGuideline: (value: string) => string;
  noGuideline: string;
  notEnoughData: string;
  partialDay: (hours: number) => string;
  /** A day, the name of the month, and the time ("11 Nov, 14:00 UTC"). */
  hour: (day: string, month: string, time: string) => string;

  // The panel of a unit.
  closePanel: string;
  loading: string;
  somethingWrong: string;
  kinds: { municipality: string; district: string; territory: string };
  emissionsCaption: (year: number) => string;
  noEmissions: (year: number) => string;
  columns: { pollutant: string; declared: string; perKm2: string; guideline: string; latest: string };
  airQuality: string;
  airUnavailable: string;
  noValues: string;
  latestValue: (hour: string) => string;
  noMeasurement: { no_station: string; no_data: string; level_not_supported: string; other: string };

  // The legend.
  legendUnitsLabel: string;
  legendStationsLabel: string;
  legendDensity: string;
  legendRatioTitle: string;
  legendGuideline: string;
  legendTwiceOrMore: string;
  legendNote: string;
  legendNoStationOrRatio: string;

  // The names of the pollutants. The API gives them in English (the dictionary of English has none of
  // the emissions): the other languages name each code, and the API name is the fallback.
  airPollutants: Record<AirCode, string>;
  pollutants: Record<string, string>;
}
