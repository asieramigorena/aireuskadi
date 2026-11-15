"""The interactive documentation (/docs, /redoc) loads scripts from other sites, so a service only
serves it when it is asked to; /openapi.json, which the gateway reads, is always there."""

import pytest
from emissions_service.main import app_from_env, create_app
from fastapi.testclient import TestClient


def test_by_default_there_is_no_interactive_documentation_but_there_is_the_openapi_document(
    client,
):
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert "/pollutants" in client.get("/openapi.json").json()["paths"]


def test_the_interactive_documentation_can_be_switched_on(engine):
    client = TestClient(create_app(engine, docs=True))

    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


@pytest.mark.parametrize("value", ["1", "true", "TRUE"])
def test_the_environment_switches_the_documentation_on(engine, monkeypatch, value):
    monkeypatch.setenv("DOCS_ENABLED", value)

    assert TestClient(app_from_env()).get("/docs").status_code == 200


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "enabled"])
def test_anything_else_in_the_environment_leaves_it_off(engine, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DOCS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DOCS_ENABLED", value)

    assert TestClient(app_from_env()).get("/docs").status_code == 404
