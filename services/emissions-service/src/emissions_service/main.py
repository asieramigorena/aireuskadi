"""Emissions REST API entry point. Routes go here; the database is read-only."""

import logging
import os
import time
from http import HTTPStatus

from aireuskadi_db import Pollutant, WhoGuideline
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from emissions_service.logs import configure_logging

access = logging.getLogger("emissions_service.access")


class GuidelineOut(BaseModel):
    averaging_period: str
    edition: int
    value_ugm3: float


class PollutantOut(BaseModel):
    code: str
    name: str
    group: str | None
    who_guidelines: list[GuidelineOut]


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="AirEuskadi Emissions Service")

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
        return JSONResponse(
            {
                "type": "about:blank",
                "title": HTTPStatus(error.status_code).phrase,
                "status": error.status_code,
                "detail": error.detail,
            },
            status_code=error.status_code,
            media_type="application/problem+json",
        )

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

    return app


def app_from_env() -> FastAPI:
    """Build the application from DATABASE_URL; uvicorn calls this with --factory."""
    configure_logging()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    return create_app(create_engine(url))
