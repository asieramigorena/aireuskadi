"""The cache of the gateway (Redis): a good answer of a service is kept for a while, and the same
question in that time does not reach the service."""

import os

import pytest
from api_gateway.cache import Cache
from api_gateway.main import create_app
from fastapi.testclient import TestClient


class FakeRedis:
    """What the gateway uses of Redis: get, and set with a time to live (`ex`, in seconds)."""

    def __init__(self):
        self.values: dict[str, bytes] = {}
        self.seconds: dict[str, int] = {}
        self.error: Exception | None = None

    async def get(self, key):
        if self.error:
            raise self.error
        return self.values.get(key)

    async def set(self, key, value, ex):
        if self.error:
            raise self.error
        self.values[key], self.seconds[key] = value, ex

    async def aclose(self):
        pass


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def cached_client(upstreams, redis):
    emissions_client, air_quality_client = upstreams
    app = create_app(emissions_client, air_quality=air_quality_client, cache=Cache(redis))
    with TestClient(app) as client:
        yield client


POINTS = "/api/v1/facilities/points?pollutant=NOX&year=2023"


def test_the_same_question_twice_reaches_the_service_once(cached_client, emissions):
    emissions.respond(body=b"[[1, 2, 3]]")

    first = cached_client.get(POINTS)
    second = cached_client.get(POINTS)

    assert len(emissions.requests) == 1
    assert first.json() == second.json() == [[1, 2, 3]]
    assert second.headers["content-type"] == "application/json"


def test_another_value_is_another_question_but_an_unknown_or_repeated_parameter_is_not(
    cached_client, emissions, redis
):
    cached_client.get(POINTS)
    cached_client.get(POINTS + "&x=1")  # never reaches the service
    cached_client.get("/api/v1/facilities/points?pollutant=NOX&year=2022&year=2023")  # the last
    cached_client.get("/api/v1/facilities/points?pollutant=SOX&year=2023")

    assert len(emissions.requests) == 2
    assert len(redis.values) == 2


def test_the_emissions_are_kept_an_hour_and_the_air_quality_five_minutes(
    cached_client, air_quality, redis
):
    air_quality.respond(body=b"{}")
    cached_client.get(POINTS)
    cached_client.get("/api/v1/stations/latest?pollutant=NO2")

    assert sorted(redis.seconds.values()) == [300, 3600]


@pytest.mark.parametrize("status", [404, 422, 500])
def test_only_a_good_answer_is_kept(cached_client, emissions, redis, status):
    emissions.respond(status=status, body=b"{}", content_type="application/problem+json")

    cached_client.get(POINTS)
    cached_client.get(POINTS)

    assert len(emissions.requests) == 2
    assert redis.values == {}


def test_the_card_of_a_unit_is_put_together_from_the_cache_too(
    cached_client, emissions, air_quality
):
    emissions.respond(body=b'{"code": "48020", "name": "Bilbao"}')
    air_quality.respond(
        body=b'{"attribution": "a", "measured": true, "reason": null, "stations": []}'
    )

    first = cached_client.get("/api/v1/units/48020")
    second = cached_client.get("/api/v1/units/48020")

    assert first.json() == second.json()
    assert second.json()["air_quality"]["measured"] is True
    assert len(emissions.requests) == len(air_quality.requests) == 1


def test_without_redis_the_gateway_answers_and_leaves_redis_alone_for_a_while(
    cached_client, emissions, redis, caplog
):
    redis.error = ConnectionError("Error connecting to redis:6379")

    first = cached_client.get(POINTS)
    second = cached_client.get(POINTS)

    assert first.status_code == second.status_code == 200
    assert len(emissions.requests) == 2
    # One failure, then 30 seconds without asking Redis; the log does not say where it is.
    assert caplog.text.count("The cache failed") == 1
    assert "redis:6379" not in caplog.text


def test_each_start_of_the_gateway_has_keys_of_its_own(redis):
    # A new version can change what an answer looks like: what an older gateway kept is not served.
    assert Cache(redis).prefix != Cache(redis).prefix


@pytest.mark.skipif(not os.environ.get("REDIS_URL"), reason="REDIS_URL is not set")
def test_it_works_with_a_real_redis(upstreams, emissions):
    import redis.asyncio as real_redis

    emissions_client, air_quality_client = upstreams
    cache = Cache(real_redis.Redis.from_url(os.environ["REDIS_URL"]))
    emissions.respond(body=b"[[9, 9, 9]]")

    with TestClient(create_app(emissions_client, air_quality=air_quality_client, cache=cache)) as c:
        first = c.get(POINTS)
        second = c.get(POINTS)

    assert first.json() == second.json() == [[9, 9, 9]]
    assert len(emissions.requests) == 1
