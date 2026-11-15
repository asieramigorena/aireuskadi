"""The health check of the gateway itself, its request log and its documentation."""

import logging

from api_gateway.main import create_app
from fastapi.testclient import TestClient

ACCESS = "api_gateway.access"


def test_the_gateway_has_its_own_health_check_that_does_not_ask_the_service(client, emissions):
    response = client.get("/health")

    # Not under /api/v1 (the browser has no use for it) and it opens no connection to the service.
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert emissions.requests == []


def test_the_interactive_documentation_is_off_unless_it_is_asked_for(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_the_description_of_the_routes_is_not_published_unless_it_is_asked_for(client):
    # The browser has no use for it, and on the internet it is the list of what can be probed.
    assert client.get("/openapi.json").status_code == 404


def test_each_request_leaves_one_record_without_the_query_string_or_the_headers(
    client, emissions, caplog
):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get(
            "/api/v1/units?level=municipality&pollutant=NOX&year=2023",
            headers={"Authorization": "Bearer secret-token"},
        )

    (record,) = [r for r in caplog.records if r.name == ACCESS]
    assert (record.method, record.path, record.status) == ("GET", "/api/v1/units", 200)
    assert "secret-token" not in str(record.__dict__)
    assert "NOX" not in str(record.__dict__)


def test_a_request_that_the_gateway_refuses_is_logged_with_its_status(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/api/v1/health")

    (record,) = [r for r in caplog.records if r.name == ACCESS]
    assert record.status == 404


def test_the_check_of_the_compose_is_only_in_the_log_at_debug(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/health")

    assert [r for r in caplog.records if r.name == ACCESS] == []


def test_the_library_that_asks_the_service_does_not_write_its_own_line_in_the_log(
    client, emissions, caplog
):
    # httpx logs the whole URL of every request it makes: the internal name and port of the
    # service and the values of the query that the client typed.
    with caplog.at_level(logging.INFO):
        client.get("/api/v1/units?level=municipality&pollutant=NOX&year=2023")

    assert [r for r in caplog.records if r.name.startswith(("httpx", "httpcore"))] == []
    assert "emissions.internal" not in caplog.text
    assert "NOX" not in caplog.text


def test_the_connections_to_both_services_are_closed_when_the_gateway_stops(upstreams):
    emissions_client, air_quality_client = upstreams

    with TestClient(create_app(emissions_client, air_quality=air_quality_client)):
        assert not emissions_client.is_closed
        assert not air_quality_client.is_closed

    assert emissions_client.is_closed
    assert air_quality_client.is_closed
