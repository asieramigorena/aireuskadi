"""GET /units: the units of a level as GeoJSON, with their indicators of a pollutant and a year."""

from datetime import date

import pytest

THIS_YEAR = date.today().year
ATTRIBUTION = "GeoEuskadi / Gobierno Vasco, CC BY 4.0, simplified"


def units(client, level="municipality", pollutant="TSTP", year=2023):
    response = client.get("/units", params={"level": level, "pollutant": pollutant, "year": year})
    assert response.status_code == 200, response.text
    # The database of the tests can hold units of other tests: only the ones of these tests.
    return {
        f["properties"]["code"]: f
        for f in response.json()["features"]
        if f["properties"]["code"].startswith("99")
    }


def test_a_municipality_comes_with_its_simplified_boundary_and_its_indicators(
    client, add_pollutant, add_facility, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    refresh_indicators()

    response = client.get(
        "/units", params={"level": "municipality", "pollutant": "TSTP", "year": 2023}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    feature = units(client)["99001"]
    assert feature["type"] == "Feature"
    # The smaller square, not the full boundary (-2.0 43.0, 0.1 wide), and [lon, lat].
    assert feature["geometry"] == {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-1.99, 43.01], [-1.91, 43.01], [-1.91, 43.09], [-1.99, 43.09], [-1.99, 43.01]]]
        ],
    }
    # 100 t over 10 km2. Nothing measured: no ratio with the WHO guideline.
    assert feature["properties"] == {
        "code": "99001",
        "name": "Testville",
        "declared_t": 100.0,
        "t_km2": 10.0,
        "who_ratio": None,
    }


def test_the_licence_of_the_boundaries_travels_with_them(client):
    response = client.get(
        "/units", params={"level": "municipality", "pollutant": "TSTP", "year": 2023}
    )

    assert response.json()["attribution"] == ATTRIBUTION


def test_a_unit_without_data_for_that_pollutant_and_year_is_there_with_nulls(
    client, add_pollutant, add_facility, refresh_indicators
):
    # Nothing declared is not the same as zero declared: the map paints it as "no data".
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    refresh_indicators()

    properties = units(client)["99002"]["properties"]

    assert properties == {
        "code": "99002",
        "name": "Testburg",
        "declared_t": None,
        "t_km2": None,
        "who_ratio": None,
    }


def test_the_data_of_another_pollutant_or_another_year_is_not_mixed_in(
    client, add_pollutant, add_facility, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_pollutant("TSTQ", "Test pollutant Q")
    add_facility(
        "T0000000A",
        -1.95,
        43.05,
        emissions=[("TSTP", 2023, "100000"), ("TSTP", 2022, "7000"), ("TSTQ", 2023, "5000")],
    )
    refresh_indicators()

    assert units(client)["99001"]["properties"]["declared_t"] == 100.0
    assert units(client, year=2022)["99001"]["properties"]["declared_t"] == 7.0
    assert units(client, pollutant="TSTQ")["99001"]["properties"]["declared_t"] == 5.0


def test_a_district_adds_up_its_municipalities_and_is_not_the_mean_of_their_densities(
    client, add_pollutant, add_facility, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    add_facility(
        "T0000000B", -1.85, 43.05, emissions=[("TSTP", 2023, "30000")], municipality="99002"
    )
    refresh_indicators()

    feature = units(client, level="district")["9901"]

    # 100 t + 30 t over 10 km2 + 30 km2. The mean of the densities (10 and 1) would be 5.5.
    assert feature["properties"] == {
        "code": "9901",
        "name": "Test district",
        "declared_t": 130.0,
        "t_km2": 3.25,
        "who_ratio": None,
    }
    assert feature["geometry"]["coordinates"] == [
        [[[-2.04, 42.96], [-1.76, 42.96], [-1.76, 43.24], [-2.04, 43.24], [-2.04, 42.96]]]
    ]


def test_a_territory_adds_up_everything_it_holds_and_divides_by_all_its_area(
    client, add_pollutant, add_facility, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    add_facility(
        "T0000000B", -1.85, 43.05, emissions=[("TSTP", 2023, "30000")], municipality="99002"
    )
    refresh_indicators()

    feature = units(client, level="territory")["99"]

    # 130 t over 10 + 30 + 60 km2: the municipality without data still has its area.
    assert feature["properties"] == {
        "code": "99",
        "name": "Test territory",
        "declared_t": 130.0,
        "t_km2": 1.3,
        "who_ratio": None,
    }
    assert feature["geometry"]["coordinates"] == [
        [[[-2.09, 42.91], [-1.71, 42.91], [-1.71, 43.29], [-2.09, 43.29], [-2.09, 42.91]]]
    ]


def test_a_district_where_nothing_was_declared_has_nulls_and_not_zeros(
    client, add_pollutant, add_facility, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    refresh_indicators()

    properties = units(client, level="district")["9902"]["properties"]

    assert properties["declared_t"] is None
    assert properties["t_km2"] is None


def test_the_data_of_a_level_does_not_appear_in_another(
    client, add_pollutant, add_facility, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    refresh_indicators()

    assert set(units(client, level="territory")) == {"99"}
    assert set(units(client, level="district")) == {"9901", "9902"}
    assert set(units(client, level="municipality")) == {"99001", "99002", "99003"}


def test_the_ratio_with_the_who_guideline_is_only_for_municipalities(
    client, add_pollutant, add_measurements, refresh_indicators
):
    # Mean of 20 and 30 = 25 µg/m3 measured in Testville over a guideline of 10. A district or a
    # territory has no ratio: how to combine the stations of its municipalities is open (issue #33).
    add_pollutant("TSTW", "Test pollutant W", guidelines=[("annual", 2021, 10)])
    add_measurements("TSTW", [20, 30])
    refresh_indicators()

    ratio = {
        level: units(client, level=level, pollutant="TSTW")[code]["properties"]["who_ratio"]
        for level, code in (("municipality", "99001"), ("district", "9901"), ("territory", "99"))
    }

    assert ratio == {"municipality": 2.5, "district": None, "territory": None}


def problem_loc(response):
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    return [error["loc"] for error in response.json()["errors"]]


GOOD = {"level": "municipality", "pollutant": "TSTP", "year": 2023}


@pytest.mark.parametrize("level", ["", "city", "Municipality", "municipalities", "99001"])
def test_a_level_that_does_not_exist_is_refused(client, level):
    response = client.get("/units", params={**GOOD, "level": level})

    assert problem_loc(response) == [["query", "level"]]


@pytest.mark.parametrize("missing", ["level", "pollutant", "year"])
def test_every_parameter_is_needed(client, missing):
    params = {k: v for k, v in GOOD.items() if k != missing}

    response = client.get("/units", params=params)

    assert problem_loc(response) == [["query", missing]]


@pytest.mark.parametrize(
    "pollutant",
    ["", "\x00", "NOX\x00", "NOX\n", "A" * 21, "NOX!", "nox", "NO X", "NOX'; DROP TABLE x;--", "Ñ"],
)
def test_a_pollutant_code_that_cannot_be_one_is_refused_before_it_reaches_the_database(
    client, pollutant
):
    response = client.get("/units", params={**GOOD, "pollutant": pollutant})

    assert problem_loc(response) == [["query", "pollutant"]]


@pytest.mark.parametrize("year", [THIS_YEAR, THIS_YEAR + 1, 99999, 0, -5])
def test_a_year_that_has_not_ended_or_is_not_a_year_is_refused(client, year):
    response = client.get("/units", params={**GOOD, "year": year})

    assert problem_loc(response) == [["query", "year"]]


def test_a_year_that_is_not_a_number_is_refused(client):
    response = client.get("/units", params={**GOOD, "year": "last"})

    assert problem_loc(response) == [["query", "year"]]


def test_a_year_before_the_first_one_with_data_is_refused_and_that_first_year_is_accepted(
    client, add_pollutant, add_facility
):
    # 1990 is earlier than anything in the real data, so it is the first year with data.
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 1990, "10")])

    before = client.get("/units", params={**GOOD, "year": 1989})
    first = client.get("/units", params={**GOOD, "year": 1990})

    assert problem_loc(before) == [["query", "year"]]
    assert first.status_code == 200


def test_the_last_year_that_has_ended_is_accepted(client):
    response = client.get("/units", params={**GOOD, "year": THIS_YEAR - 1})

    assert response.status_code == 200


@pytest.mark.parametrize("pollutant", ["A", "PM10", "CO2", "TST_1", "A" * 20])
def test_a_well_formed_pollutant_code_is_accepted_whether_it_exists_or_not(client, pollutant):
    response = client.get("/units", params={**GOOD, "pollutant": pollutant})

    assert response.status_code == 200


def test_a_pollutant_that_was_only_measured_has_no_tonnes_and_not_zero(
    client, add_pollutant, add_measurements, refresh_indicators
):
    # Measured in Testville, declared by nobody: the ratio is there, the tonnes are "no data".
    add_pollutant("TSTW", "Test pollutant W", guidelines=[("annual", 2021, 10)])
    add_measurements("TSTW", [20, 30])
    refresh_indicators()

    properties = {
        level: units(client, level=level, pollutant="TSTW")[code]["properties"]
        for level, code in (("municipality", "99001"), ("district", "9901"), ("territory", "99"))
    }

    assert properties["municipality"]["who_ratio"] == 2.5
    for level in ("municipality", "district", "territory"):
        assert properties[level]["declared_t"] is None, level
        assert properties[level]["t_km2"] is None, level
