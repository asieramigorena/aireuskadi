"""app_from_env: what uvicorn calls to build the application."""

import json
import logging

import pytest
from emissions_service.main import app_from_env
from fastapi.testclient import TestClient


def test_without_database_url_it_stops_with_a_message_that_names_it(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SystemExit) as stopped:
        app_from_env()

    assert "DATABASE_URL" in str(stopped.value)


def test_with_database_url_it_serves_what_is_in_that_database(engine, add_pollutant):
    add_pollutant("TSTS", "Started from the environment")

    response = TestClient(app_from_env()).get("/pollutants")

    assert "TSTS" in [item["code"] for item in response.json()]


def test_starting_the_application_switches_the_logs_to_json(engine, capsys):
    app_from_env()

    logging.getLogger("emissions_service.access").info("request", extra={"status": 200})

    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == 200
