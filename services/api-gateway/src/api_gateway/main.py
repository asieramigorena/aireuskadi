"""Gateway entry point: puts the application together. The routes are in routes.py."""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from aireuskadi_http import install_problem_documents, install_request_log
from aireuskadi_logger import configure_logging
from fastapi import FastAPI

from api_gateway import routes

PREFIX = "/api/v1"


def create_app(emissions: httpx.AsyncClient, *, docs: bool = False) -> FastAPI:
    """`emissions` is the client of the emissions service. The interactive pages (/docs and
    /redoc) load their scripts from other sites, so they are only there if asked."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await emissions.aclose()

    app = FastAPI(
        title="AirEuskadi API Gateway",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        # /x/ is a 404, not a redirect to /x: the redirect repeats the Host header of the request,
        # which behind the compose would give away the internal name and port of the service.
        redirect_slashes=False,
        lifespan=lifespan,
    )
    # httpx writes a line for every request it makes, with the whole URL: the internal name and port
    # of the service and the values of the query. The request log of the gateway replaces it.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app.state.emissions = emissions
    install_problem_documents(app)
    # The checks of the compose come every few seconds: they are only in the log at DEBUG.
    install_request_log(app, "api_gateway.access", quiet_paths=(routes.HEALTH_PATH,))
    app.include_router(routes.health)
    app.include_router(routes.router, prefix=PREFIX)
    return app


def app_from_env() -> FastAPI:
    """Build the application from EMISSIONS_URL. It is what the container runs: uvicorn finds it
    by name in the CMD of gateway.Dockerfile (--factory), so no Python code calls it."""
    configure_logging("api_gateway", uvicorn=True)
    emissions = httpx.AsyncClient(
        base_url=os.environ.get("EMISSIONS_URL", "http://emissions-service:8000"),
        # The service cuts its own queries after 5 s: a longer wait is a service that is stuck.
        timeout=httpx.Timeout(10.0, connect=3.0),
        follow_redirects=False,
    )
    docs = os.environ.get("DOCS_ENABLED", "").lower() in ("1", "true")
    return create_app(emissions, docs=docs)
