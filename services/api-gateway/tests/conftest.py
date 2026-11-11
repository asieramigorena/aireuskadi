"""Fixtures. The two services (emissions and air quality) are fakes that answer through
httpx.MockTransport: they are the boundary of the gateway, and they keep what the gateway sent."""

import logging
import sys

import httpx
import pytest
from api_gateway.main import create_app
from fastapi.testclient import TestClient


class FakeUpstream:
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
    return FakeUpstream()


@pytest.fixture
def air_quality():
    return FakeUpstream()


@pytest.fixture
def upstreams(emissions, air_quality):
    """The two clients of the gateway, wired to the fakes (each one with its own host)."""
    return (
        httpx.AsyncClient(
            base_url="http://emissions.internal:8000", transport=httpx.MockTransport(emissions)
        ),
        httpx.AsyncClient(
            base_url="http://air-quality.internal:8000", transport=httpx.MockTransport(air_quality)
        ),
    )


INDEX = (
    "<!doctype html><title>AirEuskadi</title>"
    '<script type="module" src="/assets/index-abc123.js"></script>'
)


@pytest.fixture
def web_dir(tmp_path):
    """A folder like the one that `npm run build` makes: the page and its assets, and a file that
    is not part of what is published."""
    site = tmp_path / "dist"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text(INDEX)
    (site / "assets" / "index-abc123.js").write_text("console.log(1);")
    (site / "assets" / "index-abc123.css").write_text("body{margin:0}")
    (site / "assets" / ".hidden").write_text("not an asset")
    (site / "secret.txt").write_text("in the folder, but not published")
    (tmp_path / "outside.txt").write_text("outside the folder")
    return site


@pytest.fixture
def web_client(upstreams, web_dir):
    emissions_client, air_quality_client = upstreams
    app = create_app(emissions_client, air_quality=air_quality_client, web_dir=web_dir)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(upstreams):
    emissions_client, air_quality_client = upstreams
    with TestClient(create_app(emissions_client, air_quality=air_quality_client)) as client:
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
