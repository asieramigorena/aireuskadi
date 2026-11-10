"""One log record per request, with the fields that Loki and the dashboards filter on."""

import logging

from emissions_service.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

ACCESS = "emissions_service.access"


def requests_logged(caplog):
    return [r for r in caplog.records if r.name == ACCESS]


def test_each_request_leaves_one_record_with_method_path_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/pollutants?year=2023")

    (record,) = requests_logged(caplog)
    assert record.getMessage() == "request"
    assert record.method == "GET"
    assert record.path == "/pollutants"  # the query string is not logged
    assert record.status == 200
    assert record.duration_ms >= 0


def test_a_request_that_ends_in_an_error_is_logged_with_its_status(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/no-such-path")

    (record,) = requests_logged(caplog)
    assert record.status == 404


def test_a_request_that_crashes_is_logged_as_a_500_without_its_query_string(caplog):
    # The route fails on purpose; the engine never connects because the route does not use it.
    app = create_app(create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none"))

    @app.get("/boom")
    def boom():
        raise RuntimeError("on purpose")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger=ACCESS):
        response = client.get("/boom?secret=1")

    assert response.status_code == 500
    (record,) = requests_logged(caplog)
    assert (record.method, record.path, record.status) == ("GET", "/boom", 500)
