"""The card of a unit: what the emissions service says, with what the air quality service says."""

import json
import logging

import httpx
import pytest

CARD = {
    "code": "48020",
    "level": "municipality",
    "name": "Bilbao",
    "area_km2": 40.594,
    "district": {"code": "4802", "name": "GRAN BILBAO"},
    "territory": {"code": "48", "name": "BIZKAIA"},
    "emissions": [
        {"year": 2026, "pollutant": "NOX", "name": "Nitrogen oxides", "declared_t": 12.5}
    ],
}
STATIONS = {
    "attribution": "Open Data Euskadi, air quality network / Gobierno Vasco, CC BY 4.0",
    "unit": {"code": "48020", "name": "Bilbao", "level": "municipality"},
    "measured": True,
    "reason": None,
    "stations": [
        {
            "id": 7,
            "code": "BI1",
            "name": "Mazarredo",
            "geometry": {"type": "Point", "coordinates": [-2.93, 43.26]},
            "readings": [{"pollutant": "NO2", "ts": "2026-11-11T14:00:00.000Z", "value": 31}],
        }
    ],
}
UNIT_URL = "/api/v1/units/48020"


@pytest.fixture
def answers(emissions, air_quality):
    """Both services answer with a real-looking body."""
    emissions.respond(body=json.dumps(CARD).encode())
    air_quality.respond(body=json.dumps(STATIONS).encode())
    return emissions, air_quality


def test_the_card_is_the_one_of_the_emissions_service_with_the_stations_of_the_air_quality_one(
    client, answers
):
    response = client.get(UNIT_URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert {k: v for k, v in body.items() if k != "air_quality"} == CARD
    assert body["air_quality"] == {
        "attribution": STATIONS["attribution"],
        "measured": True,
        "reason": None,
        "stations": STATIONS["stations"],
    }


def test_each_service_is_asked_for_its_part_of_the_unit_and_only_that(client, answers):
    emissions, air_quality = answers

    client.get(UNIT_URL + "?pollutant=NOX&year=2023&admin=1")

    (to_emissions,) = emissions.requests
    (to_air_quality,) = air_quality.requests
    assert to_emissions.url.path == "/units/48020"
    assert to_air_quality.url.path == "/units/48020/stations"
    assert not to_emissions.url.params
    assert not to_air_quality.url.params


# --- the air quality service cannot answer: the card still does -----------------------------------


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("air-quality-service: name not known"), httpx.ReadTimeout("slow")]
)
def test_without_the_air_quality_service_the_card_is_the_same_and_says_so(client, answers, error):
    _, air_quality = answers
    air_quality.error = error

    response = client.get(UNIT_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["air_quality"] is None
    assert {k: v for k, v in body.items() if k != "air_quality"} == CARD
    assert "air-quality" not in response.text


def test_only_what_the_gateway_knows_comes_from_the_air_quality_service(client, answers):
    _, air_quality = answers
    air_quality.respond(body=json.dumps({**STATIONS, "internal": "x", "debug": True}).encode())

    body = client.get(UNIT_URL).json()

    assert set(body["air_quality"]) == {"attribution", "measured", "reason", "stations"}


def test_the_failure_of_the_air_quality_service_is_in_the_log_without_its_address(
    client, answers, caplog
):
    _, air_quality = answers
    air_quality.error = httpx.ConnectError("air-quality.internal:8000 refused")

    with caplog.at_level(logging.WARNING):
        client.get(UNIT_URL)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("air quality" in r.getMessage().lower() for r in warnings)
    assert "air-quality.internal" not in caplog.text
    assert "8000" not in caplog.text


# --- the emissions service cannot answer: there is no card ---------------------------------------


@pytest.mark.parametrize("status", [404, 422])
def test_the_errors_of_the_emissions_service_come_back_as_they_are(client, answers, status):
    emissions, _ = answers
    body = json.dumps({"status": status, "detail": "about the unit"}).encode()
    emissions.respond(status, body, "application/problem+json")

    response = client.get(UNIT_URL)

    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert response.content == body


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (httpx.ConnectError("emissions-service: name not known"), 502),
        (httpx.ReadTimeout("slow"), 504),
    ],
)
def test_without_the_emissions_service_there_is_no_card_even_if_the_air_quality_one_answers(
    client, answers, error, status
):
    emissions, _ = answers
    emissions.error = error

    response = client.get(UNIT_URL)

    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert "emissions" not in response.text
    assert "air_quality" not in response.text


@pytest.mark.parametrize("body", [b"not JSON", b"[]", b'"text"'])
def test_a_card_that_is_not_an_object_is_a_502_that_says_nothing_of_the_reason(
    client, answers, body
):
    emissions, _ = answers
    emissions.respond(body=body)

    response = client.get(UNIT_URL)

    assert response.status_code == 502
    assert response.json()["detail"] == "The service is not available."
    assert "JSON" not in response.text
