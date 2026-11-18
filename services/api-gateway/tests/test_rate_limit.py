"""The limit of requests: so many per minute and per person, like rateLimit of the course example
(express-rate-limit, 100 a minute and IP). The person is the address that the tunnel says
(X-Forwarded-For, which Tailscale writes itself) or, without the tunnel, the one of the connection."""

import pytest
from api_gateway.main import create_app
from api_gateway.rate_limit import RateLimit
from fastapi.testclient import TestClient


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def limited(upstreams, web_dir, clock):
    emissions_client, air_quality_client = upstreams
    app = create_app(
        emissions_client,
        air_quality=air_quality_client,
        web_dir=web_dir,
        rate_limit=RateLimit(limit=3, clock=clock),
    )
    with TestClient(app) as client:
        yield client


def ask(client, ip="203.0.113.7", path="/api/v1/pollutants"):
    return client.get(path, headers={"X-Forwarded-For": ip})


def test_past_the_limit_of_a_minute_a_person_gets_a_429_and_the_service_is_not_asked(
    limited, emissions
):
    for _ in range(3):
        assert ask(limited).status_code == 200

    response = ask(limited)

    assert response.status_code == 429
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["retry-after"] == "60"
    assert len(emissions.requests) == 3


def test_the_limit_is_of_each_person(limited):
    for _ in range(3):
        ask(limited, ip="203.0.113.7")

    assert ask(limited, ip="198.51.100.2").status_code == 200


def test_the_next_minute_a_person_can_ask_again(limited, clock):
    for _ in range(4):
        ask(limited)

    clock.now += 60

    assert ask(limited).status_code == 200


def test_the_page_its_files_and_the_health_check_are_not_counted(limited):
    for _ in range(5):
        assert limited.get("/", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 200
        assert limited.get("/health", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 200

    assert ask(limited).status_code == 200
