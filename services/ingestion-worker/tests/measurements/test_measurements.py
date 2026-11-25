import json
from datetime import UTC, datetime

import pytest
from ingestion_worker.measurements.parse import MeasurementRecord, parse_measurements


def value(name="NO2", value=18.0, unit="µg/m3", airquality=None):
    measurement = {"name": name, "value": value, "unit": unit}
    if airquality:
        measurement["airquality"] = airquality
    return measurement


def station(code="211", *values, qualification="Buena"):
    """A station of one hour. Without `airQualityStation` the hour is a placeholder."""
    data = {"id": code, "name": f"STATION {code}", "measurements": list(values)}
    if qualification:
        data["airQualityStation"] = qualification
    return data


def hours(*items):
    """The response of the API: a list of hours, each with its stations."""
    return json.dumps([{"date": date, "station": list(stations)} for date, stations in items])


def test_a_value_has_its_station_pollutant_averaging_utc_hour_value_and_unit():
    text = hours(("2026-11-01T08:00:00Z", [station("211", value("NO2", 18.0, "µg/m3"))]))

    result = parse_measurements(text)

    assert result.accepted == [
        MeasurementRecord("211", "NO2", "1h", datetime(2026, 11, 1, 8, tzinfo=UTC), 18.0, "µg/m3")
    ]


def test_an_hour_without_air_quality_station_is_a_placeholder_and_is_skipped():
    # The API fills the hours that have not been measured yet with zeros and no qualification.
    text = hours(
        ("2026-11-01T12:00:00Z", [station("211", value("NO2", 18.0))]),
        ("2026-11-01T13:00:00Z", [station("211", value("NO2", 0.0), qualification=None)]),
    )

    result = parse_measurements(text)

    assert [(r.ts.hour, r.value) for r in result.accepted] == [(12, 18.0)]
    assert result.skipped == 1


def test_meteorological_parameters_are_not_pollutants_and_are_skipped():
    text = hours(
        (
            "2026-11-01T08:00:00Z",
            [
                station(
                    "211", value("V.vien", 3.2, "m/s"), value("Tº", 11.0, "ºC"), value("NO2", 18.0)
                )
            ],
        )
    )

    result = parse_measurements(text)

    assert [r.pollutant_code for r in result.accepted] == ["NO2"]
    assert result.rejected == []
    assert result.skipped == 2


def test_a_value_qualified_as_no_data_is_skipped_but_a_real_zero_is_kept():
    text = hours(
        (
            "2026-11-01T08:00:00Z",
            [
                station(
                    "211",
                    value("NO2", 0.0, airquality="Sin datos"),  # missing, not zero
                    value("SO2", 0.0, airquality="Muy buena"),  # a real zero
                )
            ],
        )
    )

    result = parse_measurements(text)

    assert [(r.pollutant_code, r.value) for r in result.accepted] == [("SO2", 0.0)]
    assert result.skipped == 1


def test_api_names_are_translated_and_the_hourly_and_8_hour_series_are_kept_apart():
    text = hours(
        (
            "2026-11-01T08:00:00Z",
            [
                station(
                    "211",
                    value("CO", 0.4, "mg/m3"),
                    value("CO 8h", 0.3, "mg/m3"),
                    value("PM2,5", 14.0),
                    value("M-P-XILENO", 1.2),
                )
            ],
        )
    )

    result = parse_measurements(text)

    assert {(r.pollutant_code, r.averaging_period, r.value) for r in result.accepted} == {
        ("CO", "1h", 0.4),
        ("CO", "8h", 0.3),
        ("PM25", "1h", 14.0),
        ("M_P_XYLENE", "1h", 1.2),
    }


def test_a_pollutant_name_that_is_not_known_is_rejected_and_logged_and_the_others_stay(caplog):
    text = hours(
        ("2026-11-01T08:00:00Z", [station("211", value("Mercurio", 0.1), value("NO2", 18.0))])
    )

    with caplog.at_level("WARNING", logger="ingestion_worker.measurements.parse"):
        result = parse_measurements(text)

    assert [r.pollutant_code for r in result.accepted] == ["NO2"]
    (rejected,) = result.rejected
    assert (rejected.station_code, rejected.name) == ("211", "Mercurio")
    assert "not known" in rejected.reason
    (record,) = caplog.records
    assert (record.getMessage(), record.source, record.station) == (
        "row rejected",
        "measurements",
        "211",
    )
    assert record.pollutant_name == "Mercurio"


def test_a_value_that_is_not_a_number_or_has_no_unit_is_rejected_and_logged_and_the_others_stay(
    caplog,
):
    text = hours(
        (
            "2026-11-01T08:00:00Z",
            [
                station(
                    "211",
                    value("NO2", "n/d"),
                    {"name": "O3", "value": 40.0},  # no unit
                    value("PM10", "NaN"),
                    value("SO2", 4.0),
                )
            ],
        )
    )

    with caplog.at_level("WARNING", logger="ingestion_worker.measurements.parse"):
        result = parse_measurements(text)

    assert [r.pollutant_code for r in result.accepted] == ["SO2"]
    assert [(r.name, r.reason) for r in result.rejected] == [
        ("NO2", "value is not a number"),
        ("O3", "unit is missing"),
        ("PM10", "value is not a number"),
    ]
    assert len(caplog.records) == 3


def test_an_answer_that_is_not_a_list_of_hours_stops_the_run_with_a_clear_error():
    # The API changed: nothing of it is loaded, and the error says so.
    with pytest.raises(ValueError, match="measurements answer changed"):
        parse_measurements(json.dumps({"error": "maintenance"}))
    with pytest.raises(ValueError, match="measurements answer changed"):
        parse_measurements(json.dumps([{"fecha": "2026-11-01T08:00:00Z"}]))


def test_rows_read_counts_the_values_that_are_tried_not_the_ones_that_are_not_data():
    text = hours(
        (
            "2026-11-01T08:00:00Z",
            [
                station(
                    "211",
                    value("NO2", 18.0),  # accepted
                    value("Mercurio", 0.1),  # rejected
                    value("V.vien", 3.2, "m/s"),  # skipped
                    value("SO2", 0.0, airquality="Sin datos"),  # skipped
                )
            ],
        ),
        (
            "2026-11-01T09:00:00Z",
            [station("211", value("NO2", 0.0), qualification=None)],
        ),  # skipped
    )

    result = parse_measurements(text)

    assert (len(result.accepted), len(result.rejected), result.skipped) == (1, 1, 3)
    assert result.rows_read == 2


# --- Which stations only send the weather


def test_a_station_that_sends_only_weather_is_meteorological():
    text = hours(("2026-11-01T10:00:00Z", [station("201", value("P", 1019.2), value("H", 80))]))

    assert parse_measurements(text).meteo_only == {"201": True}


def test_a_station_that_sends_a_pollutant_without_data_is_not_meteorological():
    no2 = value("NO2", 0.0, airquality="Sin datos")
    text = hours(("2026-11-01T10:00:00Z", [station("68", no2, qualification="Sin datos")]))

    assert parse_measurements(text).meteo_only == {"68": False}


def test_one_hour_with_a_pollutant_is_enough_to_not_be_meteorological():
    text = hours(
        ("2026-11-01T10:00:00Z", [station("211", value("P", 1019.2))]),
        ("2026-11-01T11:00:00Z", [station("211", value("NO2", 18.0), qualification=None)]),
    )

    assert parse_measurements(text).meteo_only == {"211": False}
