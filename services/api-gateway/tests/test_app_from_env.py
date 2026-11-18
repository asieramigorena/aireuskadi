"""app_from_env: what uvicorn calls to build the application."""

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


@pytest.mark.parametrize("service", ["emissions", "air_quality"])
def test_the_wait_for_a_service_is_short_and_a_redirect_is_not_followed(service):
    client = getattr(app_from_env().state, service)

    # The services cut their own queries after 5 s: a longer wait is a service that is stuck. A
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


def test_the_folder_of_the_page_comes_from_the_environment(monkeypatch, web_dir):
    monkeypatch.setenv("WEB_DIR", str(web_dir))

    response = TestClient(app_from_env()).get("/")

    assert response.status_code == 200
    assert "AirEuskadi" in response.text


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


def test_the_cache_is_redis_at_redis_url_and_waits_very_little(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert app_from_env().state.cache is None

    monkeypatch.setenv("REDIS_URL", "redis://cache.test:6379/0")
    cache = app_from_env().state.cache

    # A Redis that does not answer must not make every request of the page slow.
    options = cache.redis.connection_pool.connection_kwargs
    assert options["socket_connect_timeout"] <= 1 and options["socket_timeout"] <= 1


def test_the_gateway_that_runs_limits_each_person_to_120_requests_a_minute(monkeypatch):
    # How the limit works is in test_rate_limit.py, with a clock of its own; here only that the
    # gateway that runs has it, with its number (121 real requests could cross a minute and fail).
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("WEB_DIR", raising=False)

    assert app_from_env().state.rate_limit.limit == 120
