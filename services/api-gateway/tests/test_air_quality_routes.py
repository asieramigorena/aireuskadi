"""The routes of the air quality service, and that they are kept apart from the emissions ones."""

import httpx
import pytest

STATION_MEASUREMENTS = (
    "/api/v1/stations/7/measurements?pollutant=NO2&from=2026-11-01T00:00:00Z"
    "&to=2026-11-02T00:00:00Z&interval=hour"
)

ROUTES = [
    ("/api/v1/stations", "/stations"),
    ("/api/v1/stations/latest?pollutant=NO2", "/stations/latest"),
    (STATION_MEASUREMENTS, "/stations/7/measurements"),
    ("/api/v1/units/48020/exposure?pollutant=NO2&year=2026", "/units/48020/exposure"),
    ("/api/v1/units/48/exposure?pollutant=NO2&year=2026", "/units/48/exposure"),
    # The biggest id that the pattern lets through: ten digits.
    ("/api/v1/stations/9999999999/measurements?pollutant=NO2", "/stations/9999999999/measurements"),
]


@pytest.mark.parametrize(("public", "internal"), ROUTES)
def test_each_route_is_asked_to_the_air_quality_service_and_never_to_the_emissions_one(
    client, emissions, air_quality, public, internal
):
    air_quality.respond(body=b'{"answer": 42}')

    response = client.get(public)

    assert response.status_code == 200
    assert response.json() == {"answer": 42}
    (sent,) = air_quality.requests
    assert sent.url.path == internal
    assert sent.method == "GET"
    assert emissions.requests == []


@pytest.mark.parametrize(
    ("public", "expected"),
    [
        ("/api/v1/stations/latest?pollutant=NO2", {"pollutant": "NO2"}),
        (
            STATION_MEASUREMENTS,
            {
                "pollutant": "NO2",
                "from": "2026-11-01T00:00:00Z",
                "to": "2026-11-02T00:00:00Z",
                "interval": "hour",
            },
        ),
        (
            "/api/v1/units/48020/exposure?pollutant=NO2&year=2026",
            {"pollutant": "NO2", "year": "2026"},
        ),
    ],
)
def test_only_the_parameters_that_the_route_names_travel_and_with_the_value_they_had(
    client, air_quality, public, expected
):
    client.get(public + "&admin=1&debug=true")

    (sent,) = air_quality.requests
    assert dict(sent.url.params) == expected
    assert "admin" not in str(sent.url)


def test_when_the_air_quality_service_is_down_the_emissions_routes_keep_working(
    client, emissions, air_quality
):
    air_quality.error = httpx.ConnectError("down")
    emissions.respond(body=b'{"answer": 42}')

    assert client.get("/api/v1/stations").status_code == 502
    assert client.get("/api/v1/pollutants").json() == {"answer": 42}


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/api/v1/stations/abc/measurements", "station_id"),
        ("/api/v1/stations/0/measurements", "station_id"),
        ("/api/v1/stations/-1/measurements", "station_id"),
        ("/api/v1/stations/07/measurements", "station_id"),
        ("/api/v1/stations/12345678901/measurements", "station_id"),
        ("/api/v1/stations/%EF%BC%91/measurements", "station_id"),  # a full-width 1
        ("/api/v1/stations/1%0A/measurements", "station_id"),
        ("/api/v1/stations/%2e%2e/measurements", "station_id"),
        ("/api/v1/units/123/exposure", "code"),
        ("/api/v1/units/0100a/exposure", "code"),
        ("/api/v1/units/%EF%BC%91%EF%BC%92/exposure", "code"),
        ("/api/v1/units/01%0A/exposure", "code"),
        ("/api/v1/units/%2e%2e/exposure", "code"),
    ],
)
def test_an_id_or_a_code_that_cannot_be_one_is_a_422_before_it_is_sent(
    client, air_quality, path, name
):
    response = client.get(path)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert [e["loc"] for e in response.json()["errors"]] == [["path", name]]
    assert air_quality.requests == []
