// The numbers of the panel, in English, with three significant figures: the declared amounts go
// from thousands of tonnes to a few grams.
import type { Selection } from "./router";

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
