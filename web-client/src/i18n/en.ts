// English: the language of the texts that the rest of the code and its tests were written in. The
// names of the pollutants of the emissions are the ones that the API gives, so the table is empty.
import type { Texts } from "./types";

export const en: Texts = {
  decimalSeparator: ".",
  groupSeparator: ",",
  groupFrom: 4,
  months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  languageName: "English",

  mapChoiceLabel: "Choose the map",
  languageChoiceLabel: "Language",
  panelLabel: "Details of the unit",
  emissionsCredit: "Emissions: E-PRTR register, Open Data Euskadi, CC BY 4.0.",
  airCredit: (attribution) => `Air quality: ${attribution}`,
  loadingMap: "Loading the map…",
  pageNotFound: "This page does not exist.",

  serviceUnreachable: "The service cannot be reached.",
  serviceUnavailable: "The service is not available right now.",
  notFound: "That page or unit does not exist.",
  noDataForSelection: "There is no data for that pollutant and year. Try another year.",

  viewEmissions: "Emissions",
  viewAir: "Air quality",
  airPollutantLabel: "Pollutant of the air quality",
  mapLabelEmissions: "3D map of the declared industrial emissions of the Basque Country",
  mapLabelAir: "3D map of the latest air quality measured at the stations of the Basque Country",
  captionEmissions: (pollutant, year) => `Declared industrial emissions of ${pollutant} in ${year}`,
  captionAir: (pollutant) => `Latest air quality: ${pollutant}, against the WHO guideline`,

  noData: "No data",
  ratioOfGuideline: (value) => `${value}× the WHO guideline`,
  noGuideline: "No WHO guideline",
  notEnoughData: "Not enough data",
  partialDay: (hours) => `${hours} of 24 hours`,
  hour: (day, month, time) => `${day} ${month}, ${time} UTC`,

  closePanel: "Close the panel",
  loading: "Loading…",
  somethingWrong: "Something went wrong",
  kinds: { municipality: "Municipality", district: "District", territory: "Territory" },
  emissionsCaption: (year) => `Declared industrial emissions in ${year}`,
  noEmissions: (year) => `No declared emissions in ${year}.`,
  columns: { pollutant: "Pollutant", declared: "Declared", perKm2: "Per km²", guideline: "WHO guideline", latest: "Latest" },
  airQuality: "Air quality",
  airUnavailable: "Air quality is not available right now.",
  noValues: "No values yet.",
  latestValue: (hour) => `Latest value: ${hour}`,
  noMeasurement: {
    no_station: "There is no air quality station in this municipality.",
    no_data: "The stations of this municipality have no values yet.",
    level_not_supported: "Stations are shown for municipalities: choose one to see its air quality.",
    other: "There is no air quality to show for this unit.",
  },

  legendUnitsLabel: "Colour of the units",
  legendStationsLabel: "Colour of the stations",
  legendDensity: "Declared per km² of each unit",
  legendRatioTitle: "Latest value vs WHO guideline",
  legendGuideline: "1× guideline",
  legendTwiceOrMore: "2× or more",
  legendNote: "Columns: stations. Ground: mean of the stations of each municipality.",
  legendNoStationOrRatio: "No station or no ratio",

  airPollutants: {
    NO2: "Nitrogen dioxide",
    PM25: "Particles PM2.5",
    PM10: "Particles PM10",
    O3: "Ozone",
    SO2: "Sulphur dioxide",
    CO: "Carbon monoxide",
  },
  pollutants: {},
};
