"""Emissions REST API entry point: puts the application together. The routes are in the other
modules and the database is read-only."""

import os

from aireuskadi_logger import configure_logging
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine

from emissions_service import facilities, pollutants
from emissions_service.logs import install_request_log
from emissions_service.problems import install_problem_documents


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="AirEuskadi Emissions Service")
    app.state.engine = engine
    install_problem_documents(app)
    install_request_log(app)
    app.include_router(pollutants.router)
    app.include_router(facilities.router)
    return app


def app_from_env() -> FastAPI:
    """Build the application from DATABASE_URL; uvicorn calls this with --factory."""
    configure_logging("emissions_service", uvicorn=True)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    return create_app(create_engine(url))
