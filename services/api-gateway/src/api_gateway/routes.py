"""What the gateway publishes: an explicit list of routes of the emissions service and of the air
quality service.

It is not a proxy that sends everything on: a route that is not here does not exist, so the health
check and the OpenAPI document of the services cannot be reached from outside. The request to a
service is built from scratch, with nothing of the headers of the browser and only the parameters
that the route names.
"""

import asyncio
import json
import logging
from http import HTTPStatus
from typing import Annotated
from urllib.parse import urlencode

import httpx
from aireuskadi_http import problem
from fastapi import APIRouter, Path, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("api_gateway")

router = APIRouter()
health = APIRouter()

HEALTH_PATH = "/health"

# The codes that the browser puts in the path: digits only, so that nothing like `..` can change the
# path of the request to the service. A facility id has up to 10 digits; the code of a territory has
# 2, the one of a district 4 and the one of a municipality 5.
FACILITY_ID = r"^[0-9]{1,10}$"
STATION_ID = r"^[1-9][0-9]{0,9}$"
UNIT_CODE = r"^([0-9]{2}|[0-9]{4}|[0-9]{5})$"

# The answers of a service that go back as they are. Any other (a crash, "cannot reach the
# database") says things about the inside: the browser gets a fixed 502 instead.
RELAYED = {200, 404, 422}

# How long a good answer is kept in the cache, in seconds. An hour for the emissions (their units
# carry the ratio with the WHO, which comes from the hourly measurements), five minutes for the
# latest values of the air.
CACHE_SECONDS = {"emissions": 60 * 60, "air_quality": 5 * 60}


async def ask(request: Request, service: str, path: str, names: tuple = ()) -> Response:
    """Ask `service` ("emissions" or "air_quality") for `path`, with the parameters `names` of the
    request (one value of each). The answer, or a problem document if it cannot be passed on."""
    params = {name: request.query_params[name] for name in names if name in request.query_params}
    cache = request.app.state.cache
    key = f"{service}{path}?{urlencode(sorted(params.items()))}"

    if cache:
        kept = await cache.get(key)
        if kept is not None:
            return Response(kept, media_type="application/json")

    client: httpx.AsyncClient = getattr(request.app.state, service)
    try:
        answer = await client.get(path, params=params, headers={"Accept": "application/json"})
    except httpx.TimeoutException:
        return problem(HTTPStatus.GATEWAY_TIMEOUT, "The service did not answer in time.")
    except httpx.HTTPError:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    if answer.status_code not in RELAYED:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")

    if cache and answer.status_code == 200:
        await cache.set(key, answer.content, CACHE_SECONDS[service])
    # The body, the status and the content type; none of the headers of the service.
    return Response(
        answer.content,
        status_code=answer.status_code,
        media_type=answer.headers.get("content-type"),
    )


@health.get(HEALTH_PATH, include_in_schema=False)
def gateway_health():
    """For the compose. It does not ask the services: each has its own check."""
    return {"status": "ok"}


@router.get("/pollutants")
async def pollutants(request: Request):
    return await ask(request, "emissions", "/pollutants")


@router.get("/facilities/years")
async def facility_years(request: Request):
    return await ask(request, "emissions", "/facilities/years")


@router.get("/facilities/points")
async def facility_points(request: Request):
    return await ask(request, "emissions", "/facilities/points", ("pollutant", "year"))


# After /facilities/points, or "points" would be taken as an id.
@router.get("/facilities/{facility_id}")
async def facility_card(request: Request, facility_id: Annotated[str, Path(pattern=FACILITY_ID)]):
    return await ask(request, "emissions", f"/facilities/{facility_id}")


@router.get("/units")
async def units(request: Request):
    return await ask(request, "emissions", "/units", ("level", "pollutant", "year"))


# Before /units/{code}: "boundaries" would be taken as a code.
@router.get("/units/boundaries")
async def unit_boundaries(request: Request):
    return await ask(request, "emissions", "/units/boundaries", ("level",))


@router.get("/inventory")
async def inventory(request: Request):
    names = ("pollutant", "classification", "sector", "from", "to")
    return await ask(request, "emissions", "/inventory", names)


@router.get("/units/{code}")
async def unit_card(request: Request, code: Annotated[str, Path(pattern=UNIT_CODE)]):
    """The card of the emissions service with, in `air_quality`, what the stations of the unit say.
    Without the air quality service the card still comes, with `null`; without the emissions
    service there is no card. Both are asked at the same time."""
    card, stations = await asyncio.gather(
        ask(request, "emissions", f"/units/{code}"),
        ask(request, "air_quality", f"/units/{code}/stations"),
    )
    if card.status_code != 200:
        return card
    body = json_or_none(card)
    if not isinstance(body, dict):
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    body["air_quality"] = air_quality_of(stations)
    if body["air_quality"] is None:
        logger.warning("The air quality service gave nothing for the card of a unit")
    return JSONResponse(body)


def json_or_none(answer: Response):
    """The body of an answer read as JSON, or None if it is not JSON."""
    try:
        return json.loads(answer.body)
    except ValueError:
        return None


def air_quality_of(answer: Response) -> dict | None:
    """What the card shows of the stations of the unit: only these four members, so that nothing
    that the service adds later reaches the browser without the gateway knowing. None if the
    service could not be asked or did not answer what it answers when it works."""
    body = json_or_none(answer) if answer.status_code == 200 else None
    members = ("attribution", "measured", "reason", "stations")
    if not isinstance(body, dict) or not all(member in body for member in members):
        return None
    return {member: body[member] for member in members}


@router.get("/stations")
async def stations(request: Request):
    return await ask(request, "air_quality", "/stations")


@router.get("/stations/latest")
async def stations_latest(request: Request):
    return await ask(request, "air_quality", "/stations/latest", ("pollutant",))


@router.get("/stations/{station_id}/measurements")
async def station_measurements(
    request: Request, station_id: Annotated[str, Path(pattern=STATION_ID)]
):
    return await ask(
        request,
        "air_quality",
        f"/stations/{station_id}/measurements",
        ("pollutant", "from", "to", "interval"),
    )


@router.get("/units/{code}/exposure")
async def unit_exposure(request: Request, code: Annotated[str, Path(pattern=UNIT_CODE)]):
    return await ask(request, "air_quality", f"/units/{code}/exposure", ("pollutant", "year"))
