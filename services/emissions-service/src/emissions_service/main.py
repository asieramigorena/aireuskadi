"""Emissions REST API entry point: puts the application together. The routes are in the other
modules and the database is read-only."""

import os

from aireuskadi_http import install_problem_documents, install_request_log
from aireuskadi_logger import configure_logging
from fastapi import FastAPI
from sqlalchemy import Engine

from emissions_service import facilities, health, pollutants, units
from emissions_service.database import create_database_engine


def create_app(engine: Engine, *, docs: bool = False) -> FastAPI:
    """/openapi.json is always served, because the gateway reads it. The interactive pages
    (/docs and /redoc) load their scripts from other sites, so they are only there if asked."""
    app = FastAPI(
        title="AirEuskadi Emissions Service",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        # /x/ is a 404, not a redirect to /x: the redirect repeats the Host header of the request,
        # which behind the compose would give away the internal name and port of the service.
        redirect_slashes=False,
    )
    app.state.engine = engine
    install_problem_documents(app)
    # The checks of the compose come every few seconds: they are only in the log at DEBUG.
    install_request_log(app, "emissions_service.access", quiet_paths=(health.HEALTH_PATH,))
    app.include_router(health.router)
    app.include_router(pollutants.router)
    app.include_router(facilities.router)
    app.include_router(units.router)
    return app


def app_from_env() -> FastAPI:
    """Build the application from DATABASE_URL. It is what the container runs: uvicorn finds it
    by name in the CMD of emissions.Dockerfile (--factory), so no Python code calls it."""
    configure_logging("emissions_service", uvicorn=True)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    docs = os.environ.get("DOCS_ENABLED", "").lower() in ("1", "true")
    return create_app(create_database_engine(url), docs=docs)
