"""The limit of requests: so many per minute and per person. The person is the last address of
X-Forwarded-For, the one that the tunnel adds, or, without the tunnel, the one of the connection."""

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


def test_the_person_is_the_last_address_which_the_tunnel_adds_not_one_the_client_wrote(limited):
    # Cloudflare adds the address of the client at the end of an X-Forwarded-For that the client can
    # write itself: only the last one is true.
    for made_up in ("10.0.0.1", "10.0.0.2", "10.0.0.3, 10.0.0.9"):
        assert ask(limited, ip=f"{made_up}, 203.0.113.7").status_code == 200

    assert ask(limited, ip="10.0.0.4, 203.0.113.7").status_code == 429


def test_with_the_header_twice_the_person_is_the_last_address_of_the_last_one(limited):
    for made_up in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        headers = [("X-Forwarded-For", made_up), ("X-Forwarded-For", "203.0.113.7")]
        assert limited.get("/api/v1/pollutants", headers=headers).status_code == 200

    headers = [("X-Forwarded-For", "10.0.0.4"), ("X-Forwarded-For", "203.0.113.7")]
    assert limited.get("/api/v1/pollutants", headers=headers).status_code == 429


def test_the_addresses_ipv6_of_one_network_64_are_one_person(limited):
    # Whoever has one IPv6 network has millions of addresses: each one would be a new person.
    for address in ("2001:db8:1:2::1", "2001:db8:1:2::2", "2001:db8:1:2:ffff::9"):
        assert ask(limited, ip=address).status_code == 200

    assert ask(limited, ip="2001:db8:1:2::abcd").status_code == 429
    assert ask(limited, ip="2001:db8:1:3::1").status_code == 200


@pytest.mark.parametrize("path", ["/user", "/admin"])
def test_the_pages_of_the_accounts_count_in_the_limit(limited, path):
    # Each of them asks the auth service, which reads the database: a script must not ask freely.
    for _ in range(3):
        limited.get(path, headers={"X-Forwarded-For": "203.0.113.7"})

    assert ask(limited).status_code == 429


def test_grafana_has_a_limit_of_its_own_five_times_bigger(limited):
    # A dashboard asks for dozens of files and one query per panel: the limit of the API would stop
    # an admin. It is counted all the same: each request asks the auth service who the cookie is.
    grafana = [
        limited.get("/grafana/", headers={"X-Forwarded-For": "203.0.113.7"}).status_code
        for _ in range(16)
    ]

    assert 429 not in grafana[:15]
    assert grafana[15] == 429
    assert ask(limited).status_code == 200


def test_an_address_ipv4_written_as_ipv6_is_still_its_own_person(limited):
    # ::ffff:203.0.113.7 is the IPv4 203.0.113.7: all of them are not one network /64.
    for _ in range(3):
        ask(limited, ip="::ffff:203.0.113.7")

    assert ask(limited, ip="::ffff:203.0.113.7").status_code == 429
    assert ask(limited, ip="::ffff:203.0.113.8").status_code == 200
