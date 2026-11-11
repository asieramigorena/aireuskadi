// Rules that more than one route needs, in one place so that they cannot drift apart: the same
// station and pollutant must give the same answer in /stations/latest and in the time series.

// Every value in ug/m3, with its own unit (CO is published in mg/m3, the others in ug/m3). A value
// in a unit that is not known is left out of the means instead of guessed. `m` is the alias of
// core.measurement in the queries that use them.
export const TO_UGM3 = "CASE m.unit WHEN 'µg/m3' THEN 1 WHEN 'mg/m3' THEN 1000 WHEN 'ng/m3' THEN 0.001 END";
export const KNOWN_UNIT = "m.unit IN ('µg/m3', 'mg/m3', 'ng/m3')";

// A mean has enough values when it has 75 % of them, the coverage that the WHO asks for: 18 of the
// 24 hourly values of a day (or of a trailing 24 hours), and 75 % of the hours of a year.
export const MIN_COVERAGE = 0.75;
export const MIN_HOURS_FOR_A_MEAN = MIN_COVERAGE * 24;
