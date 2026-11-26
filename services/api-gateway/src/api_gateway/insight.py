"""Questions to the language model about a unit, or about what a value means in general.

The gateway checks the question (a fixed list), builds the facts from the card it already composes
(routes.compose_card), and asks the insight service. A good answer is kept in Redis under a fixed
prefix: the same question about the same data is never paid twice, and a deployment keeps them.
"""

import hashlib
import json
import re
from http import HTTPStatus
from typing import Annotated, Literal

import httpx
from aireuskadi_http import problem
from fastapi import APIRouter, Header, Path, Query, Request, Response

from api_gateway.admin import session_name
from api_gateway.routes import UNIT_CODE, ask, compose_card, json_or_none

router = APIRouter()

# Bump the version by hand when the prompt changes: the old texts are then not served any more.
INSIGHT_PREFIX = "aireuskadi:insight:v1:"
UNIT_SECONDS = 7 * 24 * 3600
GENERAL_SECONDS = 30 * 24 * 3600
NOT_AVAILABLE = "The text is not available right now."
TOO_MANY = "Too many questions right now."
TOO_MANY_LISTS = "Too many requests for the list of models right now."
TOPIC = r"^(who_ratio|density|pollutant:[A-Z0-9_]{1,20})$"

Language = Literal["eu", "es", "en"]
# The person chooses the provider from a fixed list (never an address: our server would call any
# address it is given), the model, and types the key, which comes in a header and is never kept.
Provider = Literal["groq", "openrouter", "gemini", "mistral", "ollama", "openai"]
MODEL = re.compile(r"[A-Za-z0-9._:/-]{1,100}")
Model = Annotated[str, Query(pattern=r"^[A-Za-z0-9._:/-]{1,100}$")]
LlmKey = Annotated[str, Header(pattern=r"^[!-~]{1,400}$")]
NOT_LOGGED_IN = "Log in to ask."
KEY_REFUSED = "The key was not accepted."


def unit_facts(card: dict, year: int) -> dict:
    """What the panel shows of the unit, and nothing else: the emissions of the year of the map and
    the latest values of its stations."""
    air = card.get("air_quality")
    if air is None:
        state = "not available"
    elif air.get("reason") == "level_not_supported":
        state = "not measured at this level"
    elif air.get("reason"):
        state = air["reason"].replace("_", " ")  # "no station", "no data"
    else:
        state = "measured"
    keep = ("pollutant", "value", "unit", "who_period", "who_ratio", "who_samples")
    emissions = [
        {key: e.get(key) for key in ("pollutant", "name", "declared_t", "t_km2", "who_ratio")}
        for e in card.get("emissions", [])
        if e.get("year") == year
    ]
    return {
        "name": card["name"],
        "level": card["level"],
        "district": (card.get("district") or {}).get("name"),
        "territory": (card.get("territory") or {}).get("name"),
        # Only a year that has emissions: every other year says the same (none), so it is one key
        # and not one paid text for each year that a script may ask for.
        "year": year if emissions else None,
        "emissions": emissions,
        "air_quality": state,
        "stations": [
            {
                "name": s["name"],
                # Whether it sent values in the last 7 days: a stopped station is not "current".
                "recent": s.get("recent"),
                "readings": [{key: r.get(key) for key in keep} for r in s.get("readings", [])],
            }
            for s in ((air or {}).get("stations") or [])
        ],
    }


def coarse(facts: dict) -> dict:
    """The facts without what changes every hour: a station keeps only its pollutants, their
    period and their ratio rounded to 0.1. A text is written again when the picture changes, not
    when the clock does."""
    stations = [
        {
            "name": s["name"],
            "recent": s["recent"],
            "readings": [
                {
                    "pollutant": r["pollutant"],
                    "who_period": r["who_period"],
                    "who_ratio": None if r["who_ratio"] is None else round(r["who_ratio"], 1),
                }
                for r in s["readings"]
            ],
        }
        for s in facts["stations"]
    ]
    return {**facts, "stations": stations}


# The provider and the model are in the keys: an answer is shared only with whoever asks the same
# model, so somebody's own model (a fine-tune that writes whatever they want) answers only them.
def unit_key(code: str, question: str, lang: str, provider: str, model: str, facts: dict) -> str:
    digest = hashlib.sha256(json.dumps(coarse(facts), sort_keys=True).encode()).hexdigest()
    return f"unit:{code}:{question}:{lang}:{provider}:{model}:{digest}"


def general_key(topic: str, lang: str, provider: str, model: str) -> str:
    return f"general:{topic}:{lang}:{provider}:{model}"


async def answer(
    request: Request, key: str, seconds: int, question: dict, llm: dict[str, str]
) -> Response:
    """The kept text, or a new one from the insight service (kept only if it is good). `llm` are
    the headers with the provider, the model, the key and the account: only for a new text."""
    cache = request.app.state.insight_cache
    if cache:
        kept = await cache.get(key)
        if kept is not None:
            return Response(kept, media_type="application/json")
    try:
        written = await request.app.state.insight.post("/insight", json=question, headers=llm)
    except httpx.HTTPError:
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, NOT_AVAILABLE)
    if written.status_code == 429:
        return problem(HTTPStatus.TOO_MANY_REQUESTS, TOO_MANY)
    if written.status_code == 403:
        return problem(HTTPStatus.FORBIDDEN, KEY_REFUSED)
    try:
        body = written.json()
    except ValueError:
        body = None
    if written.status_code != 200 or not isinstance(body, dict) or not body.get("text"):
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, NOT_AVAILABLE)
    # Only these two members reach the browser.
    content = json.dumps({"text": str(body["text"]), "model": str(body.get("model", ""))})
    if cache:
        await cache.set(key, content.encode(), seconds)
    return Response(content, media_type="application/json")


async def llm_headers(request: Request, provider: str, model: str, key: str) -> dict | None:
    """What the insight service needs to ask the model for this person, in headers (never in the
    body, never logged), or None without a session: only someone logged in can ask."""
    account = await session_name(request)
    if account is None:
        return None
    return {
        "X-LLM-Provider": provider,
        "X-LLM-Model": model,
        "X-LLM-Key": key,
        "X-Account": account,
    }


@router.get("/units/{code}/insight")
async def unit_insight(
    request: Request,
    code: Annotated[str, Path(pattern=UNIT_CODE)],
    question: Literal["summary", "meaning"],
    lang: Language,
    year: Annotated[int, Query(ge=1, le=9999)],
    provider: Provider,
    model: Model,
    x_llm_key: LlmKey,
):
    """A question about one unit: the text is about its card in the year of the map."""
    llm = await llm_headers(request, provider, model, x_llm_key)
    if llm is None:
        return problem(HTTPStatus.UNAUTHORIZED, NOT_LOGGED_IN)
    card = await compose_card(request, code)
    if card.status_code != 200:
        return card  # 404, 422 or the problem of the emissions service, as for the card
    facts = unit_facts(json.loads(card.body), year)
    key = unit_key(code, question, lang, provider, model, facts)
    return await answer(
        request, key, UNIT_SECONDS, {"question": question, "lang": lang, "facts": facts}, llm
    )


@router.get("/insights/{topic}")
async def general_insight(
    request: Request,
    topic: Annotated[str, Path(pattern=TOPIC)],
    lang: Language,
    provider: Provider,
    model: Model,
    x_llm_key: LlmKey,
):
    """What a value means, the same for every unit: kept once for all of them."""
    llm = await llm_headers(request, provider, model, x_llm_key)
    if llm is None:
        return problem(HTTPStatus.UNAUTHORIZED, NOT_LOGGED_IN)
    question, facts = topic, {}
    if topic.startswith("pollutant:"):
        code = topic.removeprefix("pollutant:")
        known = await ask(request, "emissions", "/pollutants")
        pollutants = json_or_none(known) if known.status_code == 200 else None
        if not isinstance(pollutants, list):
            return problem(HTTPStatus.SERVICE_UNAVAILABLE, NOT_AVAILABLE)
        found = [p for p in pollutants if isinstance(p, dict) and p.get("code") == code]
        if not found:
            return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "Unknown pollutant.")
        question = "pollutant"
        facts = {key: found[0].get(key) for key in ("code", "name", "who_guidelines")}
    return await answer(
        request,
        general_key(topic, lang, provider, model),
        GENERAL_SECONDS,
        {"question": question, "lang": lang, "facts": facts},
        llm,
    )


@router.get("/llm/models")
async def llm_models(request: Request, provider: Provider, x_llm_key: LlmKey):
    """The models that the key of the person can use at the provider, for the list of the panel.
    Not kept: the list depends on the key."""
    account = await session_name(request)
    if account is None:
        return problem(HTTPStatus.UNAUTHORIZED, NOT_LOGGED_IN)
    # The account too: the insight service counts the lists of each one.
    headers = {"X-LLM-Provider": provider, "X-LLM-Key": x_llm_key, "X-Account": account}
    try:
        answer = await request.app.state.insight.get("/models", headers=headers)
    except httpx.HTTPError:
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, NOT_AVAILABLE)
    if answer.status_code == 403:
        return problem(HTTPStatus.FORBIDDEN, KEY_REFUSED)
    if answer.status_code == 429:
        return problem(HTTPStatus.TOO_MANY_REQUESTS, TOO_MANY_LISTS)
    try:
        names = answer.json()["models"] if answer.status_code == 200 else None
    except (ValueError, KeyError, TypeError):
        names = None
    if not isinstance(names, list):
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, NOT_AVAILABLE)
    # Only names that the page can send back as a model (the pattern of `Model`).
    return {"models": [name for name in names if isinstance(name, str) and MODEL.fullmatch(name)]}
