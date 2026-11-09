"""What the gateway publishes: an explicit list of routes of the emissions service.

It is not a proxy that sends everything on: a route that is not here does not exist, so the
health check and the OpenAPI document of the service cannot be reached from outside. The request
to the service is built from scratch, with nothing of the headers of the browser and only the
parameters that the route names.
"""

from http import HTTPStatus
from typing import Annotated

import httpx
from aireuskadi_http import problem
from fastapi import APIRouter, Depends, Path, Request, Response

router = APIRouter()
health = APIRouter()

HEALTH_PATH = "/health"

# The codes that the browser puts in the path: digits only, so that nothing like `..` can walk the
# path of the request to the service to another route. A facility id has up to 10 digits; the code
# of a territory has 2, the one of a district 4 and the one of a municipality 5.
FACILITY_ID = r"^[0-9]{1,10}$"
UNIT_CODE = r"^([0-9]{2}|[0-9]{4}|[0-9]{5})$"

# The answers of the service that go back as they are: the data and its problem documents. Any
# other (a crash, a redirect, "cannot reach the database") says things about the inside.
RELAYED = {HTTPStatus.OK, HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY}


def emissions_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.emissions


Emissions = Annotated[httpx.AsyncClient, Depends(emissions_client)]


async def relay(
    emissions: httpx.AsyncClient, path: str, request: Request | None = None, names: tuple = ()
) -> Response:
    """Ask the service for `path` with the parameters `names` of the request, and give back its
    answer (the body, the status and the content type, nothing else)."""
    params = {
        n: request.query_params.getlist(n) for n in names if request and n in request.query_params
    }
    try:
        answer = await emissions.get(path, params=params, headers={"Accept": "application/json"})
    except httpx.TimeoutException:
        return problem(HTTPStatus.GATEWAY_TIMEOUT, "The service did not answer in time.")
    except httpx.HTTPError:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    if answer.status_code not in RELAYED:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    return Response(
        answer.content,
        status_code=answer.status_code,
        media_type=answer.headers.get("content-type"),
    )


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


@router.get("/units/{code}")
async def unit_card(emissions: Emissions, code: Annotated[str, Path(pattern=UNIT_CODE)]):
    return await relay(emissions, f"/units/{code}")
