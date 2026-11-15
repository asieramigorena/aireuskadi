"""GET /units/{code}: the card of one unit (municipality, district or territory) for the panel."""

import pytest


def add_data(add_pollutant, add_facility, add_measurements):
    add_pollutant("TSTP", "Test pollutant P", guidelines=[("annual", 2021, 10)])
    add_pollutant("TSTQ", "Test pollutant Q")
    add_facility(
        "T0000000A",
        -1.95,
        43.05,
        emissions=[
            ("TSTP", 2023, "100000"),
            ("TSTQ", 2023, "250000"),
            ("TSTP", 2022, "7000"),
            ("TSTQ", 2022, "500000"),  # bigger than all of 2023: the year decides first
        ],
    )
    add_facility(
        "T0000000B", -1.85, 43.05, emissions=[("TSTP", 2023, "30000")], municipality="99002"
    )
    add_measurements(
        "TSTP", [20, 30]
    )  # mean 25 µg/m3 in Testville in 2023: 2.5 times the guideline


def test_the_card_of_a_municipality(
    client, add_pollutant, add_facility, add_measurements, refresh_indicators
):
    add_data(add_pollutant, add_facility, add_measurements)
    refresh_indicators()

    response = client.get("/units/99001")

    assert response.status_code == 200
    # The latest year first and, inside a year, the biggest amount first.
    assert response.json() == {
        "code": "99001",
        "level": "municipality",
        "name": "Testville",
        "area_km2": 10.0,
        "district": {"code": "9901", "name": "Test district"},
        "territory": {"code": "99", "name": "Test territory"},
        "emissions": [
            {"year": 2023, "pollutant": "TSTQ", "name": "Test pollutant Q",
             "declared_t": 250.0, "t_km2": 25.0, "who_ratio": None},
            {"year": 2023, "pollutant": "TSTP", "name": "Test pollutant P",
             "declared_t": 100.0, "t_km2": 10.0, "who_ratio": 2.5},
            {"year": 2022, "pollutant": "TSTQ", "name": "Test pollutant Q",
             "declared_t": 500.0, "t_km2": 50.0, "who_ratio": None},
            {"year": 2022, "pollutant": "TSTP", "name": "Test pollutant P",
             "declared_t": 7.0, "t_km2": 0.7, "who_ratio": None},
        ],
    }  # fmt: skip


def test_the_card_of_a_district_adds_up_its_municipalities(
    client, add_pollutant, add_facility, add_measurements, refresh_indicators
):
    add_data(add_pollutant, add_facility, add_measurements)
    refresh_indicators()

    body = client.get("/units/9901").json()

    # 100 t + 30 t over 10 km2 + 30 km2, and no ratio with the WHO above the municipality.
    assert body["code"] == "9901"
    assert body["level"] == "district"
    assert body["area_km2"] == 40.0
    assert body["district"] is None
    assert body["territory"] == {"code": "99", "name": "Test territory"}
    assert body["emissions"][1] == {
        "year": 2023, "pollutant": "TSTP", "name": "Test pollutant P",
        "declared_t": 130.0, "t_km2": 3.25, "who_ratio": None,
    }  # fmt: skip
    assert [e["who_ratio"] for e in body["emissions"]] == [None] * 4


def test_the_card_of_a_territory_divides_by_all_its_area(
    client, add_pollutant, add_facility, add_measurements, refresh_indicators
):
    add_data(add_pollutant, add_facility, add_measurements)
    refresh_indicators()

    body = client.get("/units/99").json()

    # 130 t over 10 + 30 + 60 km2.
    assert (body["level"], body["area_km2"], body["district"], body["territory"]) == (
        "territory",
        100.0,
        None,
        None,
    )
    assert body["emissions"][1]["declared_t"] == 130.0
    assert body["emissions"][1]["t_km2"] == 1.3


def test_a_unit_that_declared_nothing_has_an_empty_list(client, add_facility, refresh_indicators):
    add_facility("T0000000A", -1.95, 43.05)  # creates the test units
    refresh_indicators()

    response = client.get("/units/99003")

    assert response.status_code == 200
    assert response.json()["emissions"] == []


@pytest.mark.parametrize("code", ["99999", "9999", "98"])
def test_a_code_that_does_not_exist_is_a_404(client, code):
    response = client.get(f"/units/{code}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(
    "code",
    ["abc", "1", "123", "123456", "0100a", "-1001", "１２", "99001%0A", "99 01", "9.1", "00000x"],
)
def test_a_code_that_cannot_be_the_one_of_a_unit_is_a_422_before_it_reaches_the_database(
    client, code
):
    response = client.get(f"/units/{code}")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert [e["loc"] for e in response.json()["errors"]] == [["path", "code"]]


def test_a_pollutant_that_was_only_measured_is_listed_after_the_declared_ones_with_no_tonnes(
    client, add_pollutant, add_facility, add_measurements, refresh_indicators
):
    add_pollutant("TSTP", "Test pollutant P")
    add_pollutant("TSTW", "Test pollutant W", guidelines=[("annual", 2021, 10)])
    add_facility("T0000000A", -1.95, 43.05, emissions=[("TSTP", 2023, "100000")])
    add_measurements("TSTW", [20, 30])  # measured in 2023, declared by nobody
    refresh_indicators()

    emissions = client.get("/units/99001").json()["emissions"]

    assert emissions == [
        {"year": 2023, "pollutant": "TSTP", "name": "Test pollutant P",
         "declared_t": 100.0, "t_km2": 10.0, "who_ratio": None},
        {"year": 2023, "pollutant": "TSTW", "name": "Test pollutant W",
         "declared_t": None, "t_km2": None, "who_ratio": 2.5},
    ]  # fmt: skip
