"""Insight service entry point: one route, POST /insight, that the gateway calls with a question
of the fixed list and the facts of a unit (or none). It answers the text of the language model.

The person brings the provider, the model and their own key, which the gateway passes in headers:
the key is used for this call and never kept or logged. Each account can ask `per_hour` questions an
hour, well or not, so nobody uses the site as a free relay."""

import logging
import time
from http import HTTPStatus
from typing import Annotated, Literal

import httpx
from aireuskadi_http import install_problem_documents, install_request_log, problem
from aireuskadi_logger import configure_logging
from fastapi import FastAPI, Header
from pydantic import BaseModel

from insight_service.llm import KeyRefused, Llm, LlmUnavailable, ProviderBusy
from insight_service.prompts import system_prompt

logger = logging.getLogger("insight_service")

HEALTH_PATH = "/health"
NOT_AVAILABLE = "The text is not available right now."
KEY_REFUSED = "The key was not accepted."
TOO_MANY = "Too many questions right now."

# The ids of llm.PROVIDERS: anything else is a 422 and nothing is called.
Provider = Literal["groq", "openrouter", "gemini", "mistral", "ollama", "openai"]


class Question(BaseModel):
    question: Literal["summary", "meaning", "who_ratio", "density", "pollutant"]
    lang: Literal["eu", "es", "en"]
    facts: dict


def refusal_for(error: LlmUnavailable):
    """What the gateway is told when the provider failed: never what the provider said."""
    if isinstance(error, KeyRefused):
        return problem(HTTPStatus.FORBIDDEN, KEY_REFUSED)
    if isinstance(error, ProviderBusy):
        return problem(HTTPStatus.TOO_MANY_REQUESTS, TOO_MANY)
    return problem(HTTPStatus.SERVICE_UNAVAILABLE, NOT_AVAILABLE)


def create_app(llm: Llm, *, per_hour: int = 30, clock=time.monotonic) -> FastAPI:
    app = FastAPI(
        title="AirEuskadi Insight Service",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    install_problem_documents(app)
    install_request_log(app, "insight_service.access", quiet_paths=(HEALTH_PATH,))
    # How many questions each account asked in the hour that is going on, like the limit of the
    # gateway (rate_limit.py): a new hour starts every count again.
    counts = {"hour": None, "asked": {}}

    @app.post("/insight")
    async def insight(
        question: Question,
        x_llm_provider: Annotated[Provider, Header()],
        x_llm_model: Annotated[str, Header(pattern=r"^[A-Za-z0-9._:/-]{1,100}$")],
        x_llm_key: Annotated[str, Header(pattern=r"^[!-~]{1,400}$")],
        x_account: Annotated[str, Header(max_length=64)],
    ):
        hour = int(clock() // 3600)
        if hour != counts["hour"]:
            counts["hour"], counts["asked"] = hour, {}
        asked = counts["asked"]
        if asked.get(x_account, 0) >= per_hour:
            return problem(HTTPStatus.TOO_MANY_REQUESTS, TOO_MANY)
        asked[x_account] = asked.get(x_account, 0) + 1

        start = time.monotonic()
        rules = system_prompt(question.question, question.lang)
        text, refusal, provider_status = None, None, None
        try:
            text = await llm.write(rules, question.facts, x_llm_provider, x_llm_model, x_llm_key)
            outcome = "written"
        except LlmUnavailable as error:
            outcome, provider_status, refusal = str(error), error.status, refusal_for(error)
        # Never the key, the prompt or the text: only what was asked and how it went.
        logger.info(
            "question",
            extra={
                "question": question.question,
                "lang": question.lang,
                "provider": x_llm_provider,
                "outcome": outcome,
                # The HTTP status of the provider when it failed (401, 429, 500...), to know why.
                "provider_status": provider_status,
                "duration_ms": round((time.monotonic() - start) * 1000),
            },
        )
        if text is None:
            return refusal
        return {"text": text, "model": x_llm_model}

    @app.get("/models")
    async def models(
        x_llm_provider: Annotated[Provider, Header()],
        x_llm_key: Annotated[str, Header(pattern=r"^[!-~]{1,400}$")],
    ):
        """The models that the key of the person can use at the provider: the list of the panel,
        so that nobody asks a model that does not exist."""
        try:
            return {"models": await llm.models(x_llm_provider, x_llm_key)}
        except LlmUnavailable as error:
            logger.info(
                "models",
                extra={
                    "provider": x_llm_provider,
                    "outcome": str(error),
                    "provider_status": error.status,
                },
            )
            return refusal_for(error)

    @app.get(HEALTH_PATH, include_in_schema=False)
    def health():
        return {"status": "ok"}

    return app


def app_from_env() -> FastAPI:
    """Build the application. It is what the container runs: uvicorn finds it by name in the CMD
    of insight.Dockerfile (--factory). Nothing to configure: the provider, the model and the key
    come with each question."""
    configure_logging("insight_service", uvicorn=True)
    # A new connection for each question: a kept one is closed by the provider after a while
    # without questions, and the next question would fail on it.
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=5.0),
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    return create_app(Llm(client=client))
