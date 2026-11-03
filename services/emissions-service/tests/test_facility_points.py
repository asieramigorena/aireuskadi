"""GET /facilities/points: [lon, lat, kg] of every facility that declared a pollutant in a year."""

from datetime import date

import pytest
from sqlalchemy import text

THIS_YEAR = date.today().year


def test_points_are_lon_lat_kg_of_the_facilities_that_declared_that_pollutant_that_year(
    client, add_pollutant, add_facility
):
    add_pollutant("TSTP", "Test pollutant P")
    add_pollutant("TSTQ", "Test pollutant Q")
    add_facility(
        "T0000000A",
        -2.9,
        43.2,
        emissions=[("TSTP", 2023, "500.5"), ("TSTP", 2022, "999"), ("TSTQ", 2023, "777")],
    )
    add_facility("T0000000B", -2.8, 43.3, emissions=[("TSTP", 2023, "1500")])
    add_facility("T0000000C", -2.7, 43.4, emissions=[("TSTQ", 2023, "5")])

    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": 2023})

    assert response.status_code == 200
    # Longitude first (the Basque Country is at negative longitudes, latitude about 43),
    # the biggest emitter first, and nothing from another pollutant or another year.
    assert response.json() == [[-2.8, 43.3, 1500.0], [-2.9, 43.2, 500.5]]


def test_no_data_is_an_empty_list_not_an_error(client, add_pollutant):
    add_pollutant("TSTP", "Test pollutant P")

    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": 2023})

    assert response.status_code == 200
    assert response.json() == []


def test_a_facility_without_a_position_is_left_out_instead_of_breaking_the_answer(
    client, add_pollutant, add_facility
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", None, None, emissions=[("TSTP", 2023, "900")])
    add_facility("T0000000B", -2.8, 43.3, emissions=[("TSTP", 2023, "100")])

    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": 2023})

    assert response.status_code == 200
    assert response.json() == [[-2.8, 43.3, 100.0]]


def problem_loc(response):
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    return [error["loc"] for error in response.json()["errors"]]


@pytest.mark.parametrize("year", [THIS_YEAR, THIS_YEAR + 1, 99999])
def test_a_year_that_has_not_ended_yet_is_refused(client, year):
    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": year})

    assert problem_loc(response) == [["query", "year"]]


@pytest.mark.parametrize("year", [0, -5])
def test_a_year_below_one_is_refused(client, year):
    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": year})

    assert problem_loc(response) == [["query", "year"]]


def test_the_last_year_that_has_ended_is_accepted(client, add_pollutant):
    add_pollutant("TSTP", "Test pollutant P")

    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": THIS_YEAR - 1})

    assert response.status_code == 200
    assert response.json() == []


def test_a_year_before_the_first_one_with_data_is_refused_and_that_first_year_is_accepted(
    client, add_pollutant, add_facility
):
    # 1990 is earlier than anything in the real data, so it is the first year with data.
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -2.8, 43.3, emissions=[("TSTP", 1990, "10")])

    before = client.get("/facilities/points", params={"pollutant": "TSTP", "year": 1989})
    first = client.get("/facilities/points", params={"pollutant": "TSTP", "year": 1990})

    assert problem_loc(before) == [["query", "year"]]
    assert first.status_code == 200
    assert first.json() == [[-2.8, 43.3, 10.0]]


def test_facilities_with_the_same_amount_always_come_out_in_the_same_order(
    engine, client, add_pollutant, add_facility
):
    add_pollutant("TSTP", "Test pollutant P")
    add_facility("T0000000A", -2.1, 43.1, emissions=[("TSTP", 2023, "100")])
    add_facility("T0000000B", -2.2, 43.2, emissions=[("TSTP", 2023, "100")])
    # Rewriting the first row moves it after the second one in the table, so without a
    # tie-breaker the order of the answer would follow the table and not the facilities.
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE core.facility_emission SET amount_kg = amount_kg WHERE facility_id = "
                "(SELECT id FROM core.facility WHERE nima = 'T0000000A')"
            )
        )

    response = client.get("/facilities/points", params={"pollutant": "TSTP", "year": 2023})

    assert response.json() == [[-2.1, 43.1, 100.0], [-2.2, 43.2, 100.0]]


def test_a_pollutant_that_does_not_exist_is_an_empty_list_not_a_404(client):
    response = client.get("/facilities/points", params={"pollutant": "TSTNONE", "year": 2023})

    assert response.status_code == 200
    assert response.json() == []
