"""What the gateway publishes: an explicit list of routes of the emissions service and of the air
quality service.

It is not a proxy that sends everything on: a route that is not here does not exist, so the
health check and the OpenAPI document of the services cannot be reached from outside. The request
to a service is built from scratch, with nothing of the headers of the browser and only the
parameters that the route names. Each route belongs to one service: once the gateway is running, if
one is down the routes of the other keep working.
"""

import asyncio
import logging
from http import HTTPStatus
from typing import Annotated

import httpx
from aireuskadi_http import problem
from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("api_gateway")

router = APIRouter()
health = APIRouter()

HEALTH_PATH = "/health"

# The codes that the browser puts in the path: digits only, so that nothing like `..` can walk the
# path of the request to the service to another route. A facility id has up to 10 digits; the code
# of a territory has 2, the one of a district 4 and the one of a municipality 5. A station id has
# no leading zero (the air quality service takes it as it is).
FACILITY_ID = r"^[0-9]{1,10}$"
STATION_ID = r"^[1-9][0-9]{0,9}$"
UNIT_CODE = r"^([0-9]{2}|[0-9]{4}|[0-9]{5})$"

# The answers of the service that go back as they are: the data and its problem documents. Any
# other (a crash, a redirect, "cannot reach the database") says things about the inside.
RELAYED = {HTTPStatus.OK, HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY}


def emissions_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.emissions


def air_quality_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.air_quality


Emissions = Annotated[httpx.AsyncClient, Depends(emissions_client)]
AirQuality = Annotated[httpx.AsyncClient, Depends(air_quality_client)]


async def ask(
    service: httpx.AsyncClient, path: str, request: Request | None = None, names: tuple = ()
) -> httpx.Response | Response:
    """Ask a service (its client is `service`) for `path` with the parameters `names` of the
    request. It gives back the answer if it can be passed on (see RELAYED), and otherwise the
    problem document that goes to the browser instead: the reason of the failure stays inside."""
    params = {
        n: request.query_params.getlist(n) for n in names if request and n in request.query_params
    }
    try:
        answer = await service.get(path, params=params, headers={"Accept": "application/json"})
    except httpx.TimeoutException:
        return problem(HTTPStatus.GATEWAY_TIMEOUT, "The service did not answer in time.")
    except httpx.HTTPError:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    if answer.status_code not in RELAYED:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    return answer


def passed_on(answer: httpx.Response) -> Response:
    """The answer of a service as it goes to the browser: the body, the status and the content type,
    nothing else (not its headers)."""
    return Response(
        answer.content,
        status_code=answer.status_code,
        media_type=answer.headers.get("content-type"),
    )


async def relay(
    service: httpx.AsyncClient, path: str, request: Request | None = None, names: tuple = ()
) -> Response:
    """Ask a service for `path` and give back its answer as it is."""
    answer = await ask(service, path, request, names)
    return passed_on(answer) if isinstance(answer, httpx.Response) else answer


@health.get(HEALTH_PATH, include_in_schema=False)
def gateway_health():
    """For the compose. It does not ask the service: its own check is the one of the compose."""
    return {"status": "ok"}


@router.get("/pollutants")
async def pollutants(emissions: Emissions):
    return await relay(emissions, "/pollutants")


@router.get("/facilities/points")
async def facility_points(request: Request, emissions: Emissions):
    return await relay(emissions, "/facilities/points", request, ("pollutant", "year"))


# This route has to come after /facilities/points, or "points" would be taken as an id.
@router.get("/facilities/{facility_id}")
async def facility_card(
    emissions: Emissions, facility_id: Annotated[str, Path(pattern=FACILITY_ID)]
):
    return await relay(emissions, f"/facilities/{facility_id}")


@router.get("/units")
async def units(request: Request, emissions: Emissions):
    return await relay(emissions, "/units", request, ("level", "pollutant", "year"))


# What the card takes from the answer of the air quality service: only these, so that nothing that
# the service adds later reaches the browser without the gateway knowing.
AIR_QUALITY_MEMBERS = ("attribution", "measured", "reason", "stations")


def air_quality_of(answer: httpx.Response | Response) -> dict | None:
    """The stations of a unit as the card shows them, or None if there is nothing to show: the
    service could not be asked, or what it said is not what it says when it works."""
    if not isinstance(answer, httpx.Response) or answer.status_code != HTTPStatus.OK:
        return None
    try:
        body = answer.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or not set(AIR_QUALITY_MEMBERS) <= body.keys():
        return None
    # The members are checked for their type too: the web page trusts them.
    if not isinstance(body["measured"], bool):
        return None
    if body["stations"] is not None and not isinstance(body["stations"], list):
        return None
    return {name: body[name] for name in AIR_QUALITY_MEMBERS}


@router.get("/units/{code}")
async def unit_card(
    emissions: Emissions, air_quality: AirQuality, code: Annotated[str, Path(pattern=UNIT_CODE)]
):
    """The card of the emissions service, and in `air_quality` what the stations of the unit say.
    The card is what matters: without the air quality service it still answers, with `null`; without
    the emissions service there is no card. Both are asked at the same time on purpose: the common
    case is that both answer, and waiting for one before the other would add their times."""
    card, stations = await asyncio.gather(
        ask(emissions, f"/units/{code}"), ask(air_quality, f"/units/{code}/stations")
    )
    if not isinstance(card, httpx.Response):
        return card
    if card.status_code != HTTPStatus.OK:
        return passed_on(card)
    try:
        body = card.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    body["air_quality"] = air_quality_of(stations)
    if body["air_quality"] is None:
        # No address, no reason: the log of the request has the rest.
        logger.warning("The air quality service gave nothing for the card of a unit")
    return JSONResponse(body)


@router.get("/stations")
async def stations(air_quality: AirQuality):
    return await relay(air_quality, "/stations")


@router.get("/stations/latest")
async def stations_latest(request: Request, air_quality: AirQuality):
    return await relay(air_quality, "/stations/latest", request, ("pollutant",))


@router.get("/stations/{station_id}/measurements")
async def station_measurements(
    request: Request,
    air_quality: AirQuality,
    station_id: Annotated[str, Path(pattern=STATION_ID)],
):
    return await relay(
        air_quality,
        f"/stations/{station_id}/measurements",
        request,
        ("pollutant", "from", "to", "interval"),
    )


@router.get("/units/{code}/exposure")
async def unit_exposure(
    request: Request, air_quality: AirQuality, code: Annotated[str, Path(pattern=UNIT_CODE)]
):
    return await relay(air_quality, f"/units/{code}/exposure", request, ("pollutant", "year"))
