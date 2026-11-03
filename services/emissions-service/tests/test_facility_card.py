"""GET /facilities/{id}: the card of one facility with its declared emissions."""

import pytest


def test_the_card_has_the_facility_its_municipality_and_only_its_own_emissions(
    client, add_pollutant, add_facility
):
    add_pollutant("TSTP", "Test pollutant P")
    add_pollutant("TSTQ", "Test pollutant Q")
    facility_id = add_facility(
        "T0000000A",
        -2.9,
        43.2,
        name="Test plant",
        activity="Test activity",
        emissions=[("TSTP", 2022, "10"), ("TSTP", 2023, "500.5"), ("TSTQ", 2023, "700")],
    )
    add_facility("T0000000B", -2.8, 43.3, emissions=[("TSTP", 2023, "999")])

    response = client.get(f"/facilities/{facility_id}")

    assert response.status_code == 200
    # Emissions: latest year first and, inside a year, the biggest amount first.
    assert response.json() == {
        "id": facility_id,
        "nima": "T0000000A",
        "name": "Test plant",
        "activity": "Test activity",
        "location": {"lon": -2.9, "lat": 43.2},
        "municipality": {"code": "99001", "name": "Testville"},
        "emissions": [
            {"year": 2023, "pollutant": "TSTQ", "name": "Test pollutant Q", "kg": 700.0},
            {"year": 2023, "pollutant": "TSTP", "name": "Test pollutant P", "kg": 500.5},
            {"year": 2022, "pollutant": "TSTP", "name": "Test pollutant P", "kg": 10.0},
        ],
    }


def test_a_facility_without_a_position_or_emissions_still_has_a_card(client, add_facility):
    facility_id = add_facility("T0000000A", None, None)

    response = client.get(f"/facilities/{facility_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["location"] is None
    assert body["activity"] is None
    assert body["emissions"] == []


def test_emissions_of_the_same_year_and_amount_come_out_ordered_by_pollutant(
    client, add_pollutant, add_facility
):
    add_pollutant("TSTA", "Test pollutant A")
    add_pollutant("TSTB", "Test pollutant B")
    facility_id = add_facility(
        "T0000000A", -2.9, 43.2, emissions=[("TSTB", 2023, "5"), ("TSTA", 2023, "5")]
    )

    response = client.get(f"/facilities/{facility_id}")

    assert [e["pollutant"] for e in response.json()["emissions"]] == ["TSTA", "TSTB"]


def test_a_facility_that_does_not_exist_is_a_404_problem(client):
    response = client.get("/facilities/2000000000")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Facility 2000000000 not found.",
    }


@pytest.mark.parametrize(
    "facility_id", ["abc", "0", "-1", "2147483648", "99999999999999999999", "1.5"]
)
def test_an_id_that_cannot_be_one_is_a_422_that_names_it(client, facility_id):
    response = client.get(f"/facilities/{facility_id}")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert [error["loc"] for error in response.json()["errors"]] == [["path", "facility_id"]]


@pytest.mark.parametrize("facility_id", [1, 2147483647])
def test_the_smallest_and_the_biggest_possible_ids_are_valid_ids(client, facility_id):
    # Whether such a facility exists depends on the data: it is a 200 or a 404, never a 422.
    assert client.get(f"/facilities/{facility_id}").status_code in (200, 404)
