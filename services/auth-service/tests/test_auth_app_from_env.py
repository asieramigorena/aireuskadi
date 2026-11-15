"""app_from_env: what uvicorn calls to build the service."""

import pytest
from auth_service.main import app_from_env

# Nothing is asked to the database to build the application.
URL = "postgresql+psycopg://user1:pw@127.0.0.1:1/x"


def test_a_short_secret_stops_the_start(monkeypatch):
    monkeypatch.setenv("AUTH_DATABASE_URL", URL)
    monkeypatch.setenv("JWT_SECRET", "too-short")

    with pytest.raises(SystemExit, match="JWT_SECRET"):
        app_from_env()


def test_without_the_database_it_does_not_start(monkeypatch):
    monkeypatch.delenv("AUTH_DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    with pytest.raises(SystemExit, match="AUTH_DATABASE_URL"):
        app_from_env()
