"""Fixtures. The emissions service is a fake that answers through httpx.MockTransport: it is the
boundary of the gateway, and it keeps what the gateway sent."""

import logging
import sys

import httpx
import pytest
from api_gateway.main import create_app
from fastapi.testclient import TestClient


class FakeEmissions:
    """What the gateway sent (`requests`) and what the fake answers (`respond`)."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.body = b"[]"
        self.content_type = "application/json"
        self.headers: dict[str, str] = {}
        self.error: Exception | None = None

    def respond(self, status=200, body=b"[]", content_type="application/json", headers=None):
        self.status, self.body, self.content_type = status, body, content_type
        self.headers = headers or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        return httpx.Response(
            self.status,
            content=self.body,
            headers={"content-type": self.content_type, **self.headers},
        )


@pytest.fixture
def emissions():
    return FakeEmissions()


@pytest.fixture
def client(emissions):
    upstream = httpx.AsyncClient(
        base_url="http://emissions.internal:8000", transport=httpx.MockTransport(emissions)
    )
    with TestClient(create_app(upstream)) as client:
        yield client


@pytest.fixture(autouse=True)
def keep_logging_state():
    """app_from_env sets up the logging (the root logger, uvicorn's, sys.excepthook): put it back
    after the test."""
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx"]
    saved = [(n, logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in names]
    level, hook = logging.getLogger().level, sys.excepthook
    httpx_level = logging.getLogger("httpx").level
    yield
    logging.getLogger("httpx").setLevel(httpx_level)
    for name, handlers, propagate in saved:
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate
    logging.getLogger().setLevel(level)
    sys.excepthook = hook
