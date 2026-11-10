"""app_from_env: what uvicorn calls to build the application."""

import json
import logging

import pytest
from api_gateway.main import app_from_env
from fastapi.testclient import TestClient


def test_the_emissions_service_is_asked_at_its_name_in_the_compose_unless_told_otherwise(
    monkeypatch,
):
    monkeypatch.delenv("EMISSIONS_URL", raising=False)

    app = app_from_env()

    assert str(app.state.emissions.base_url) == "http://emissions-service:8000"


def test_the_environment_says_where_the_emissions_service_is(monkeypatch):
    monkeypatch.setenv("EMISSIONS_URL", "http://other-host:9000")

    app = app_from_env()

    assert str(app.state.emissions.base_url) == "http://other-host:9000"


def test_the_wait_for_the_service_is_short_and_a_redirect_is_not_followed():
    client = app_from_env().state.emissions

    # The service cuts its own queries after 5 s: a longer wait is a service that is stuck. A
    # redirect would take the gateway to wherever the service says.
    assert client.timeout.read == 10.0
    assert client.timeout.connect == 3.0
    assert client.follow_redirects is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE"])
def test_the_environment_switches_the_documentation_on(monkeypatch, value):
    monkeypatch.setenv("DOCS_ENABLED", value)

    client = TestClient(app_from_env())

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "enabled"])
def test_anything_else_in_the_environment_leaves_it_off(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DOCS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DOCS_ENABLED", value)

    client = TestClient(app_from_env())

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_starting_the_application_switches_the_logs_to_json(capsys):
    app_from_env()

    logging.getLogger("api_gateway.access").info("request", extra={"status": 200})

    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == 200


def test_under_uvicorn_the_starting_application_takes_over_uvicorns_own_log_handlers(capsys):
    # uvicorn installs its own plain-text handler before it loads the application.
    uvicorn = logging.getLogger("uvicorn")
    uvicorn.addHandler(logging.StreamHandler())
    uvicorn.propagate = False

    app_from_env()
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    captured = capsys.readouterr()
    (entry,) = [json.loads(line) for line in captured.out.splitlines()]
    assert entry["message"] == "Application startup complete."
    assert captured.err == ""  # no second copy in plain text


def test_the_folder_of_the_page_comes_from_the_environment(monkeypatch, web_dir):
    monkeypatch.setenv("WEB_DIR", str(web_dir))

    response = TestClient(app_from_env()).get("/")

    assert response.status_code == 200
    assert "AirEuskadi" in response.text


def test_without_the_variable_the_gateway_publishes_only_the_api(monkeypatch):
    monkeypatch.delenv("WEB_DIR", raising=False)

    assert TestClient(app_from_env()).get("/").status_code == 404


@pytest.mark.parametrize("problem", ["missing", "no-index"])
def test_a_folder_that_cannot_be_published_stops_the_start_with_a_message_that_names_it(
    monkeypatch, tmp_path, problem
):
    # Better to fail when it starts than to answer a 404 to everyone later.
    folder = tmp_path / "nothing" if problem == "missing" else tmp_path
    monkeypatch.setenv("WEB_DIR", str(folder))

    with pytest.raises(SystemExit) as stopped:
        app_from_env()

    assert "WEB_DIR" in str(stopped.value)
