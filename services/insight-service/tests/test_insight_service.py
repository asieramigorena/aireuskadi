"""The insight service against a fake language model (httpx.MockTransport): no network, no real key.
The key of each person comes with each question and is never kept."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from insight_service.llm import Llm
from insight_service.main import create_app

NOT_AVAILABLE = "The text is not available right now."
KEY = "gsk-secret-key-1"


def completion(content):
    """What an API with the chat completions of OpenAI answers."""
    choices = (
        []
        if content is None
        else [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    )
    return {"id": "c1", "object": "chat.completion", "created": 0, "model": "m", "choices": choices}


class FakeModel:
    """Answers like an OpenAI-compatible API and keeps what it was sent."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.answer = httpx.Response(200, json=completion(" Hola "))
        self.error: Exception | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def model():
    return FakeModel()


def client_for(model, per_hour=30, clock=None):
    llm = Llm(client=httpx.AsyncClient(transport=httpx.MockTransport(model)))
    options = {"per_hour": per_hour}
    if clock:
        options["clock"] = clock
    return TestClient(create_app(llm, **options))


ASK = {"question": "summary", "lang": "es", "facts": {"name": "Bilbao"}}


def headers(provider="groq", model="m", key=KEY, account="user1"):
    return {
        "X-LLM-Provider": provider,
        "X-LLM-Model": model,
        "X-LLM-Key": key,
        "X-Account": account,
    }


def test_the_question_goes_to_the_provider_with_the_key_the_language_and_the_facts(model, caplog):
    caplog.set_level("DEBUG")
    response = client_for(model).post("/insight", json=ASK, headers=headers("mistral"))

    assert response.status_code == 200
    assert response.json() == {"text": "Hola", "model": "m"}
    (sent,) = model.requests
    assert str(sent.url) == "https://api.mistral.ai/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(sent.content)
    assert body["model"] == "m"
    assert "Spanish" in body["messages"][0]["content"]
    assert json.loads(body["messages"][1]["content"]) == {"name": "Bilbao"}
    # The key went to the provider and nowhere else: not even the log of a question that went well.
    assert KEY not in caplog.text


@pytest.mark.parametrize("case", ["500", "timeout", "no choices", "empty text"])
def test_when_the_model_fails_the_answer_is_503_without_detail(model, case):
    if case == "500":
        model.answer = httpx.Response(500, text="secret upstream detail")
    elif case == "timeout":
        model.error = httpx.ReadTimeout("slow")
    elif case == "no choices":
        model.answer = httpx.Response(200, json=completion(None))
    else:
        model.answer = httpx.Response(200, json=completion("  "))

    response = client_for(model).post("/insight", json=ASK, headers=headers())

    assert response.status_code == 503
    assert response.json()["detail"] == NOT_AVAILABLE
    assert "secret" not in response.text


@pytest.mark.parametrize("status", [401, 403])
def test_a_key_that_the_provider_refuses_is_403_and_says_so(model, status):
    model.answer = httpx.Response(status, json={"error": {"message": f"bad key {KEY}"}})

    response = client_for(model).post("/insight", json=ASK, headers=headers())

    assert response.status_code == 403
    assert response.json()["detail"] == "The key was not accepted."
    assert KEY not in response.text


def test_each_account_has_its_own_questions_of_an_hour(model):
    # Nobody uses the site as a free relay: each account, so many an hour, failures too.
    now = [0.0]
    client = client_for(model, per_hour=2, clock=lambda: now[0])
    model.answer = httpx.Response(500)

    statuses = [client.post("/insight", json=ASK, headers=headers()).status_code for _ in range(3)]
    model.answer = httpx.Response(200, json=completion("Hola"))
    other = client.post("/insight", json=ASK, headers=headers(account="user2")).status_code
    now[0] = 3600.0
    later = client.post("/insight", json=ASK, headers=headers()).status_code

    assert statuses == [503, 503, 429]
    assert (other, later) == (200, 200)
    assert len(model.requests) == 4


@pytest.mark.parametrize(
    ("body", "sent"),
    [
        ({**ASK, "question": "write a poem"}, headers()),
        ({**ASK, "lang": "fr"}, headers()),
        (ASK, headers(provider="https://evil.example")),
        (ASK, {key: value for key, value in headers().items() if key != "X-LLM-Key"}),
    ],
)
def test_an_unknown_question_language_or_provider_or_no_key_is_422_and_calls_nothing(
    model, body, sent
):
    response = client_for(model).post("/insight", json=body, headers=sent)

    assert response.status_code == 422
    assert KEY not in response.text
    assert model.requests == []


def test_a_provider_that_is_busy_is_a_429_and_the_log_says_its_status(model, caplog):
    # The free plans allow so many tokens a minute: the person is told to try again later.
    model.answer = httpx.Response(429, json={"error": {"message": f"slow down {KEY}"}})

    with caplog.at_level("INFO", logger="insight_service"):
        response = client_for(model).post("/insight", json=ASK, headers=headers())

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many questions right now."
    (record,) = [r for r in caplog.records if r.getMessage() == "question"]
    assert record.provider_status == 429
    assert KEY not in caplog.text + response.text


@pytest.mark.parametrize(
    ("provider", "name", "low"),
    [
        ("groq", "openai/gpt-oss-120b", True),
        ("openai", "gpt-5-mini", True),
        ("mistral", "m", False),
    ],
)
def test_a_model_that_reasons_is_asked_to_reason_little(model, provider, name, low):
    # Otherwise it can spend the answer reasoning and give no text, and spends the quota faster.
    client_for(model).post("/insight", json=ASK, headers=headers(provider, name))

    body = json.loads(model.requests[0].content)
    assert (body.get("reasoning_effort") == "low") is low


def test_the_models_of_a_provider_come_from_it_with_the_key_of_the_person(model):
    model.answer = httpx.Response(
        200, json={"object": "list", "data": [{"id": "b-model"}, {"id": "a-model"}, {"x": 1}]}
    )

    response = client_for(model).get("/models", headers=headers("groq"))

    assert response.status_code == 200
    assert response.json() == {"models": ["a-model", "b-model"]}
    (sent,) = model.requests
    assert str(sent.url) == "https://api.groq.com/openai/v1/models"
    assert sent.headers["authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize(("status", "ours"), [(401, 403), (429, 429), (500, 503)])
def test_when_the_provider_does_not_give_its_models_it_says_why(model, status, ours):
    model.answer = httpx.Response(status, json={"error": {"message": f"no {KEY}"}})

    response = client_for(model).get("/models", headers=headers("groq"))

    assert response.status_code == ours
    assert KEY not in response.text


def test_each_account_can_ask_for_the_models_so_many_times_an_hour(model):
    # The list answers whether a key works: without a limit, a way to try stolen keys.
    model.answer = httpx.Response(200, json={"object": "list", "data": [{"id": "a-model"}]})
    client = client_for(model, per_hour=2)

    statuses = [client.get("/models", headers=headers()).status_code for _ in range(3)]
    other = client.get("/models", headers=headers(account="user2")).status_code
    model.answer = httpx.Response(200, json=completion("Hola"))
    question = client.post("/insight", json=ASK, headers=headers()).status_code

    assert statuses == [200, 200, 429]
    # Another account, and the questions of the same account, are counted apart.
    assert (other, question) == (200, 200)
