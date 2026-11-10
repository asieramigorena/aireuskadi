"""What the gateway publishes: an explicit list of routes of the emissions service."""

import pytest

ROUTES = [
    ("/api/v1/pollutants", "/pollutants"),
    ("/api/v1/facilities/points?pollutant=NOX&year=2023", "/facilities/points"),
    ("/api/v1/facilities/12", "/facilities/12"),
    ("/api/v1/units?level=municipality&pollutant=NOX&year=2023", "/units"),
    ("/api/v1/units/01036", "/units/01036"),
    ("/api/v1/units/9901", "/units/9901"),
    ("/api/v1/units/48", "/units/48"),
]


@pytest.mark.parametrize(("public", "internal"), ROUTES)
def test_each_published_route_is_asked_to_the_emissions_service_and_its_answer_comes_back(
    client, emissions, public, internal
):
    emissions.respond(body=b'{"answer": 42}')

    response = client.get(public)

    assert response.status_code == 200
    assert response.json() == {"answer": 42}
    (sent,) = emissions.requests
    assert sent.url.path == internal
    assert sent.method == "GET"


def test_the_parameters_of_a_route_travel_to_the_emissions_service(client, emissions):
    client.get("/api/v1/units?level=district&pollutant=NOX&year=2023")

    (sent,) = emissions.requests
    assert dict(sent.url.params) == {"level": "district", "pollutant": "NOX", "year": "2023"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/health",
        "/api/v1/openapi.json",
        "/api/v1/docs",
        "/api/v1/inventory",
        "/api/v1/pollutants/",
        "/api/v1/units/",
        "/api/v1/units/01036/extra",
        "/api/v1/facilities/points/",
        "/pollutants",
        "/units/01036",
        "/api/v2/units",
        "/",
    ],
)
def test_anything_that_is_not_in_the_list_is_a_404_and_never_reaches_the_service(
    client, emissions, path
):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert emissions.requests == []


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_only_get_is_published(client, emissions, method):
    response = getattr(client, method)("/api/v1/units?level=municipality&pollutant=NOX&year=1")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert emissions.requests == []


def test_a_path_with_a_trailing_slash_is_a_404_not_a_redirect_that_repeats_the_host(
    client, emissions
):
    # A redirect would send the browser to whatever the Host header says, and behind the compose
    # it would give away the internal name and port of the service.
    response = client.get(
        "/api/v1/pollutants/", headers={"host": "evil.example:99"}, follow_redirects=False
    )

    assert response.status_code == 404
    assert "location" not in response.headers
