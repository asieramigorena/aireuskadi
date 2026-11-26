"""Questions to the language model: the gateway checks them, sends the facts of the unit to the
insight service and keeps the answer in Redis."""

import json

import httpx
import pytest
from api_gateway.cache import Cache
from api_gateway.insight import unit_facts, unit_key
from api_gateway.main import create_app
from fastapi.testclient import TestClient

READING = {
    "pollutant": "NO2",
    "ts": "2026-11-25T08:00:00Z",
    "value": 31,
    "unit": "µg/m3",
    "who_period": "24h",
    "who_ratio": 0.62,
    "who_samples": 24,
}
CARD = {
    "code": "48020",
    "level": "municipality",
    "name": "Bilbao",
    "area_km2": 40.6,
    "district": {"code": "4802", "name": "GRAN BILBAO"},
    "territory": {"code": "48", "name": "BIZKAIA"},
    "emissions": [
        {
            "year": 2023,
            "pollutant": "NOX",
            "name": "Nitrogen oxides",
            "declared_t": 12.5,
            "t_km2": 0.3,
            "who_ratio": None,
        },
        {
            "year": 2022,
            "pollutant": "NOX",
            "name": "Nitrogen oxides",
            "declared_t": 99.0,
            "t_km2": 2.4,
            "who_ratio": None,
        },
    ],
}
STATIONS = {
    "attribution": "x",
    "measured": True,
    "reason": None,
    "stations": [
        {"id": 7, "code": "BI1", "name": "Mazarredo", "recent": True, "readings": [READING]}
    ],
}
POLLUTANTS = [{"code": "NO2", "name": "Nitrogen dioxide", "who_guidelines": [{"period": "24h"}]}]
ANSWER = {"text": "Bilbao emite sobre todo NOX.", "model": "m"}
UNIT = "/api/v1/units/48020/insight?question=summary&lang=es&provider=groq&model=openai/gpt-oss-120b&year=2023"


class FakeRedis:
    def __init__(self):
        self.kept = {}
        self.down = False

    async def get(self, key):
        if self.down:
            raise ConnectionError("down")
        return self.kept.get(key)

    async def set(self, key, value, ex):
        if self.down:
            raise ConnectionError("down")
        self.kept[key] = value

    async def aclose(self):
        pass


@pytest.fixture
def redis():
    return FakeRedis()


KEY = "gsk-secret-key-1"


@pytest.fixture
def ask(upstreams, emissions, air_quality, insight, redis, auth):
    """A gateway with the insight service, Redis and the auth service behind it, and a browser
    that is logged in (the fake auth service says the cookie is user1) and has typed its key."""
    insight.respond(body=json.dumps(ANSWER).encode())
    emissions_client, air_quality_client = upstreams
    app = create_app(
        emissions_client,
        air_quality=air_quality_client,
        cache=Cache(redis),
        auth_client=httpx.AsyncClient(
            base_url="http://auth.internal:8000", transport=httpx.MockTransport(auth)
        ),
        insight=httpx.AsyncClient(
            base_url="http://insight.internal:8000", transport=httpx.MockTransport(insight)
        ),
    )
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("aireuskadi_session", "the-jwt")
        client.headers["X-LLM-Key"] = KEY
        yield client


def sent(insight):
    (request,) = insight.requests
    return json.loads(request.content)


def test_a_unit_question_sends_the_facts_of_the_year_and_keeps_the_answer(
    ask, emissions, air_quality, insight
):
    emissions.respond(body=json.dumps(CARD).encode())
    air_quality.respond(body=json.dumps(STATIONS).encode())

    first = ask.get(UNIT)
    second = ask.get(UNIT)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == ANSWER
    body = sent(insight)  # the second one came from Redis
    assert (body["question"], body["lang"]) == ("summary", "es")
    assert [e["declared_t"] for e in body["facts"]["emissions"]] == [12.5]
    station = body["facts"]["stations"][0]
    # Whether it sent values in the last 7 days: a station that stopped is not described as current.
    assert (station["recent"], station["readings"][0]["pollutant"]) == (True, "NO2")


def test_only_the_text_and_the_model_reach_the_browser_and_the_cache(
    ask, emissions, air_quality, insight, redis
):
    # Whatever else the insight service answered would be kept for everyone for days.
    emissions.respond(body=json.dumps(CARD).encode())
    air_quality.respond(body=json.dumps(STATIONS).encode())
    insight.respond(body=json.dumps({**ANSWER, "key": KEY, "debug": "inside"}).encode())

    answer = ask.get(UNIT)

    assert answer.json() == ANSWER
    assert redis.kept
    for kept in redis.kept.values():
        assert KEY not in str(kept) and "inside" not in str(kept)


def test_a_new_hourly_value_does_not_make_a_new_key_but_a_new_ratio_does():
    later = {**READING, "ts": "2026-11-25T09:00:00Z", "value": 33}
    higher = {**READING, "who_ratio": 0.75}

    def key(reading):
        stations = {**STATIONS, "stations": [{"name": "Mazarredo", "readings": [reading]}]}
        facts = unit_facts({**CARD, "air_quality": stations}, 2023)
        return unit_key("48020", "summary", "es", "groq", "m", facts)

    assert key(later) == key(READING)
    assert key(higher) != key(READING)


def test_a_general_question_has_no_unit_and_is_shared(ask, emissions, insight, redis):
    emissions.respond(body=json.dumps(POLLUTANTS).encode())

    for _ in range(2):
        assert (
            ask.get(
                "/api/v1/insights/pollutant:NO2?lang=es&provider=groq&model=openai/gpt-oss-120b"
            ).json()
            == ANSWER
        )

    body = sent(insight)
    assert body["question"] == "pollutant"
    assert body["facts"]["code"] == "NO2"
    assert any(
        key.endswith("general:pollutant:NO2:es:groq:openai/gpt-oss-120b") for key in redis.kept
    )
    assert (
        ask.get(
            "/api/v1/insights/pollutant:ZZZ?lang=es&provider=groq&model=openai/gpt-oss-120b"
        ).status_code
        == 422
    )
    assert len(insight.requests) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/units/48020/insight?question=hack&lang=es&provider=groq&model=openai/gpt-oss-120b&year=2023",
        "/api/v1/units/48020/insight?question=summary&lang=fr&provider=groq&model=openai/gpt-oss-120b&year=2023",
        "/api/v1/units/48020/insight?question=summary&lang=es&provider=groq&model=openai/gpt-oss-120b&year=abc",
        "/api/v1/insights/pollutant:no2?lang=es&provider=groq&model=openai/gpt-oss-120b",
        "/api/v1/insights/poem?lang=es&provider=groq&model=openai/gpt-oss-120b",
    ],
)
def test_a_bad_question_language_or_year_is_422_and_calls_nothing(ask, insight, path):
    assert ask.get(path).status_code == 422
    assert insight.requests == []


@pytest.mark.parametrize("status", [503, 429, "down"])
def test_when_the_insight_service_fails_nothing_is_kept(
    ask, emissions, air_quality, insight, redis, status
):
    emissions.respond(body=json.dumps(CARD).encode())
    air_quality.respond(body=json.dumps(STATIONS).encode())
    if status == "down":
        insight.error = httpx.ConnectError("down")
    else:
        insight.respond(status=status, body=b'{"detail": "inside"}')

    response = ask.get(UNIT)

    assert response.status_code == (429 if status == 429 else 503)
    assert "inside" not in response.text
    assert not [key for key in redis.kept if key.startswith("aireuskadi:insight:")]


def test_without_redis_the_question_still_gets_its_answer(ask, emissions, air_quality, redis):
    emissions.respond(body=json.dumps(CARD).encode())
    air_quality.respond(body=json.dumps(STATIONS).encode())
    redis.down = True

    assert ask.get(UNIT).json() == ANSWER


def test_without_air_quality_the_facts_say_so(ask, emissions, air_quality, insight):
    emissions.respond(body=json.dumps(CARD).encode())
    air_quality.error = httpx.ConnectError("down")

    assert ask.get(UNIT).status_code == 200
    assert sent(insight)["facts"]["air_quality"] == "not available"


def test_a_year_without_emissions_is_one_key_for_all_such_years():
    # A script asking year=1, 2, 3... must not make a new key (and a paid call) for each one.
    card = {**CARD, "air_quality": STATIONS}
    keys = {
        unit_key("48020", "summary", "es", "groq", "m", unit_facts(card, year))
        for year in (1, 1500, 9999)
    }

    assert len(keys) == 1
    assert unit_key("48020", "summary", "es", "groq", "m", unit_facts(card, 2023)) not in keys


@pytest.mark.parametrize("cookie", [None, "forged"])
def test_without_a_session_the_answer_is_401_and_no_model_is_asked(ask, auth, insight, cookie):
    ask.cookies.clear()
    if cookie:
        ask.cookies.set("aireuskadi_session", cookie)
        auth.respond(status=401, body=b'{"detail": "Not logged in."}')

    answer = ask.get("/api/v1/insights/who_ratio?lang=es&provider=groq&model=m")

    assert answer.status_code == 401
    assert insight.requests == []


def test_the_key_goes_to_the_insight_service_only_in_its_header_and_never_to_the_log(
    ask, insight, caplog
):
    with caplog.at_level("DEBUG"):
        assert (
            ask.get("/api/v1/insights/who_ratio?lang=es&provider=groq&model=m").status_code == 200
        )

    (request,) = insight.requests
    assert request.headers["x-llm-key"] == KEY
    assert (request.headers["x-llm-provider"], request.headers["x-llm-model"]) == ("groq", "m")
    assert request.headers["x-account"] == "user1"
    assert KEY not in request.content.decode()
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    "query", ["provider=other&model=m", "provider=groq&model=a b", "provider=groq"]
)
def test_a_bad_provider_or_model_is_422_and_never_repeats_the_key(ask, insight, query):
    answer = ask.get(f"/api/v1/insights/who_ratio?lang=es&{query}")

    assert answer.status_code == 422
    assert KEY not in answer.text
    assert insight.requests == []


def test_a_key_that_is_not_one_line_of_visible_characters_is_422(ask, insight):
    answer = ask.get(
        "/api/v1/insights/who_ratio?lang=es&provider=groq&model=m", headers={"X-LLM-Key": "a b"}
    )

    assert answer.status_code == 422
    assert insight.requests == []


def test_an_answer_is_shared_only_with_whoever_asks_the_same_provider_and_model(ask, insight):
    # Somebody's own model (a fine-tune that writes whatever they want) must not answer everyone.
    for model in ("m", "m", "my-own-model", "m"):
        assert (
            ask.get(f"/api/v1/insights/who_ratio?lang=es&provider=groq&model={model}").status_code
            == 200
        )

    assert len(insight.requests) == 2


def test_a_key_that_the_provider_refused_is_a_403_that_says_so_and_nothing_is_kept(
    ask, insight, redis
):
    insight.respond(status=403, body=b'{"detail": "inside"}')

    answer = ask.get("/api/v1/insights/who_ratio?lang=es&provider=groq&model=m")

    assert answer.status_code == 403
    assert answer.json()["detail"] == "The key was not accepted."
    assert not [key for key in redis.kept if key.startswith("aireuskadi:insight:")]


def test_the_models_of_a_provider_need_a_session_and_go_with_the_key_only_in_a_header(ask, insight):
    insight.respond(body=b'{"models": ["a-model", "b-model", 7]}')

    answer = ask.get("/api/v1/llm/models?provider=groq")

    assert answer.status_code == 200
    assert answer.json() == {"models": ["a-model", "b-model"]}
    (request,) = insight.requests
    assert request.url.path == "/models"
    assert (request.headers["x-llm-provider"], request.headers["x-llm-key"]) == ("groq", KEY)
    # Who asks: the insight service counts the lists of each account.
    assert request.headers["x-account"] == "user1"
    ask.cookies.clear()
    assert ask.get("/api/v1/llm/models?provider=groq").status_code == 401


@pytest.mark.parametrize(("status", "ours"), [(403, 403), (429, 429), (500, 503)])
def test_when_the_models_cannot_be_listed_it_says_why(ask, insight, status, ours):
    insight.respond(status=status, body=b'{"detail": "inside"}')

    answer = ask.get("/api/v1/llm/models?provider=groq")

    assert answer.status_code == ours
    assert "inside" not in answer.text
