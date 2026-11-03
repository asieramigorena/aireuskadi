"""GET /health: for the healthcheck of the compose. It is not part of the public API."""

import logging

from emissions_service.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine


def broken_app():
    """An application whose database cannot be reached (nothing listens on that port)."""
    return create_app(create_engine("postgresql+psycopg://nobody:SECRETPW@127.0.0.1:1/none"))


def test_it_says_ok_when_the_database_answers(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_it_is_a_503_problem_that_says_nothing_about_why_when_the_database_does_not_answer():
    response = TestClient(broken_app()).get("/health")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "detail": "The service cannot reach the database.",
    }
    # Nothing of the connection: not the host, the port, the user or the password.
    for secret in ("127.0.0.1", "nobody", "SECRETPW", "none"):
        assert secret not in response.text.replace("Service Unavailable", "")


def test_it_is_not_in_the_public_api_document(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/health" not in paths


def test_the_checks_of_the_compose_do_not_fill_the_request_log(client, caplog):
    with caplog.at_level(logging.INFO, logger="emissions_service.access"):
        client.get("/health")
        client.get("/pollutants")

    assert [r.path for r in caplog.records if r.name == "emissions_service.access"] == [
        "/pollutants"
    ]


def test_they_are_in_the_log_when_the_level_is_debug(client, caplog):
    with caplog.at_level(logging.DEBUG, logger="emissions_service.access"):
        client.get("/health")

    assert [r.path for r in caplog.records if r.name == "emissions_service.access"] == ["/health"]
