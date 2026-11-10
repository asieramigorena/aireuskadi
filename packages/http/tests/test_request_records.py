"""One log record per request, with the fields that Loki and the dashboards filter on."""

import logging

import pytest
from aireuskadi_http import install_request_log
from fastapi import FastAPI
from fastapi.testclient import TestClient

ACCESS = "some_service.access"


def make_client(**options):
    app = FastAPI()
    install_request_log(app, ACCESS, **options)

    @app.get("/things")
    def things():
        return []

    @app.get("/boom")
    def boom():
        raise RuntimeError("on purpose")

    return TestClient(app, raise_server_exceptions=False)


def records(caplog):
    return [r for r in caplog.records if r.name == ACCESS]


def test_each_request_leaves_one_record_with_method_path_status_and_duration(caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        make_client().get("/things?secret=1")

    (record,) = records(caplog)
    assert record.getMessage() == "request"
    assert record.method == "GET"
    assert record.path == "/things"  # the query string can carry what the client typed
    assert record.status == 200
    assert record.duration_ms >= 0


def test_a_request_that_ends_in_an_error_is_logged_with_its_status(caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        make_client().get("/no-such-path")

    (record,) = records(caplog)
    assert record.status == 404


def test_a_request_that_crashes_is_logged_as_a_500_without_its_query_string(caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        response = make_client().get("/boom?secret=1")

    assert response.status_code == 500
    (record,) = records(caplog)
    assert (record.method, record.path, record.status) == ("GET", "/boom", 500)


def test_the_paths_that_are_asked_every_few_seconds_are_only_in_the_log_at_debug(caplog):
    client = make_client(quiet_paths=("/things",))

    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/things")
    assert records(caplog) == []

    with caplog.at_level(logging.DEBUG, logger=ACCESS):
        client.get("/things")
    (record,) = records(caplog)
    assert record.levelno == logging.DEBUG


@pytest.mark.parametrize("path", ["/other", "/no-such-path"])
def test_the_other_paths_are_logged_at_info_even_if_some_are_quiet(caplog, path):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        make_client(quiet_paths=("/things",)).get(path)

    (record,) = records(caplog)
    assert record.levelno == logging.INFO
