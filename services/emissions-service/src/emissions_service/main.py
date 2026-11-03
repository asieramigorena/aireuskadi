"""Emissions REST API entry point. Routes go here; the database is read-only."""

import logging
import os
import time
from datetime import date
from http import HTTPStatus
from typing import Annotated

from aireuskadi_db import Facility, FacilityEmission, Pollutant, WhoGuideline
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from emissions_service.logs import configure_logging

access = logging.getLogger("emissions_service.access")


class ValidationErrorOut(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationProblem(BaseModel):
    """application/problem+json (RFC 9457) answer for a request with invalid parameters."""

    type: str
    title: str
    status: int
    detail: str
    errors: list[ValidationErrorOut]


# For the routes that take parameters: describes the 422 as it is sent, instead of FastAPI's
# own {"detail": [...]}, which is what the OpenAPI document would say otherwise.
INVALID_REQUEST = {422: {"model": ValidationProblem}}


class GuidelineOut(BaseModel):
    averaging_period: str
    edition: int
    value_ugm3: float


class PollutantOut(BaseModel):
    code: str
    name: str
    group: str | None
    who_guidelines: list[GuidelineOut]


def problem(status: HTTPStatus, detail: str, **extra) -> JSONResponse:
    """An error as application/problem+json (RFC 9457); `extra` adds members to the document."""
    return JSONResponse(
        {
            "type": "about:blank",
            "title": status.phrase,
            "status": status.value,
            "detail": detail,
            **extra,
        },
        status_code=status.value,
        media_type="application/problem+json",
    )


def refuse_year_out_of_range(year: int, session: Session) -> None:
    """A year that has not ended yet, or is earlier than the first one with emissions, has no
    data to ask for: refuse it with a 422 instead of answering an empty list."""
    last = date.today().year - 1
    first = session.scalar(select(func.min(FacilityEmission.year)))
    if year > last:
        problem = {"type": "less_than_equal", "msg": f"Input should be at most {last}"}
    elif first is not None and year < first:
        problem = {"type": "greater_than_equal", "msg": f"Input should be at least {first}"}
    else:
        return
    raise RequestValidationError([{**problem, "loc": ("query", "year"), "input": year}])


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="AirEuskadi Emissions Service")
    generate_openapi = app.openapi

    def openapi() -> dict:
        """FastAPI describes a response model as application/json: the problem documents are
        sent as application/problem+json, so that is how they are described."""
        spec = generate_openapi()
        for path in spec["paths"].values():
            for operation in path.values():
                content = operation["responses"].get("422", {}).get("content", {})
                if "application/json" in content:
                    content["application/problem+json"] = content.pop("application/json")
        return spec

    app.openapi = openapi

    @app.exception_handler(RequestValidationError)
    def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return problem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "The request has invalid or missing parameters.",
            errors=[
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()
            ],
        )

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        access.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        return problem(HTTPStatus(error.status_code), error.detail)

    @app.get("/pollutants")
    def pollutants() -> list[PollutantOut]:
        with Session(engine) as session:
            rows = session.scalars(select(Pollutant).order_by(Pollutant.code)).all()
            guidelines: dict[str, list[GuidelineOut]] = {}
            for g in session.scalars(select(WhoGuideline)):
                guidelines.setdefault(g.pollutant_code, []).append(
                    GuidelineOut(
                        averaging_period=g.averaging_period,
                        edition=g.edition,
                        value_ugm3=g.value_ugm3,
                    )
                )
            return [
                PollutantOut(
                    code=p.code,
                    name=p.name,
                    group=p.group,
                    who_guidelines=guidelines.get(p.code, []),
                )
                for p in rows
            ]

    @app.get("/facilities/points", responses=INVALID_REQUEST)
    def facility_points(pollutant: str, year: Annotated[int, Query(ge=1)]) -> list[list[float]]:
        """[lon, lat, kg] of each facility that declared the pollutant in the year, the biggest
        emitter first. The year has to be one that has ended and not earlier than the first year
        with data."""
        with Session(engine) as session:
            refuse_year_out_of_range(year, session)
            # TODO: add Index(pollutant_code, year) to FacilityEmission in packages/db when the
            # register grows: the primary key (facility_id, pollutant_code, year) cannot serve
            # this lookup, so today it reads the whole table (fine at ~1,700 rows).
            rows = session.execute(
                select(
                    func.ST_X(Facility.geom), func.ST_Y(Facility.geom), FacilityEmission.amount_kg
                )
                .join(FacilityEmission, FacilityEmission.facility_id == Facility.id)
                .where(
                    FacilityEmission.pollutant_code == pollutant,
                    FacilityEmission.year == year,
                    Facility.geom.is_not(None),
                )
                .order_by(FacilityEmission.amount_kg.desc(), Facility.id)
            )
            return [[lon, lat, float(kg)] for lon, lat, kg in rows]

    return app


def app_from_env() -> FastAPI:
    """Build the application from DATABASE_URL; uvicorn calls this with --factory."""
    configure_logging()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    return create_app(create_engine(url))
