"""Gateway entry point: puts the application together. The routes are in routes.py."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from aireuskadi_http import install_problem_documents, install_request_log
from aireuskadi_logger import configure_logging
from fastapi import FastAPI

from api_gateway import routes
from api_gateway.web import web_router

PREFIX = "/api/v1"


def create_app(
    emissions: httpx.AsyncClient,
    *,
    air_quality: httpx.AsyncClient,
    docs: bool = False,
    web_dir: Path | None = None,
) -> FastAPI:
    """`emissions` and `air_quality` are the clients of the two services behind the gateway. The
    interactive pages (/docs and /redoc) load their scripts from other sites, so they and
    /openapi.json are only there if asked. `web_dir` is the folder of the compiled web page;
    without it the gateway publishes only the API (in development the page comes from Vite)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await emissions.aclose()
        await air_quality.aclose()

    app = FastAPI(
        title="AirEuskadi API Gateway",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        # The description of the routes is the list of what can be probed: it goes with the pages.
        openapi_url="/openapi.json" if docs else None,
        # /x/ is a 404, not a redirect to /x: the redirect repeats the Host header of the request,
        # which behind the compose would give away the internal name and port of the service.
        redirect_slashes=False,
        lifespan=lifespan,
    )
    # httpx writes a line for every request it makes, with the whole URL: the internal name and port
    # of the service and the values of the query. The request log of the gateway replaces it.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app.state.emissions = emissions
    app.state.air_quality = air_quality
    install_problem_documents(app)
    # The checks of the compose come every few seconds: they are only in the log at DEBUG.
    install_request_log(app, "api_gateway.access", quiet_paths=(routes.HEALTH_PATH,))
    app.include_router(routes.health)
    app.include_router(routes.router, prefix=PREFIX)
    if web_dir:
        app.include_router(web_router(web_dir))
    return app


def service_client(variable: str, default: str) -> httpx.AsyncClient:
    """The client of one service: its address comes from the environment `variable`."""
    return httpx.AsyncClient(
        base_url=os.environ.get(variable, default),
        # The services cut their own queries after 5 s: a longer wait is a service that is stuck.
        timeout=httpx.Timeout(10.0, connect=3.0),
        follow_redirects=False,
    )


def app_from_env() -> FastAPI:
    """Build the application from EMISSIONS_URL and AIR_QUALITY_URL (and WEB_DIR). It is what the
    container runs: uvicorn finds it by name in the CMD of gateway.Dockerfile (--factory), so no
    Python code calls it."""
    configure_logging("api_gateway", uvicorn=True)
    emissions = service_client("EMISSIONS_URL", "http://emissions-service:8000")
    air_quality = service_client("AIR_QUALITY_URL", "http://air-quality-service:8000")
    docs = os.environ.get("DOCS_ENABLED", "").lower() in ("1", "true")
    return create_app(emissions, air_quality=air_quality, docs=docs, web_dir=web_dir_from_env())


def web_dir_from_env() -> Path | None:
    """The folder of the compiled page, if WEB_DIR names one. A folder that is not there is a
    mistake that stops the start: better than a 404 for everybody later."""
    value = os.environ.get("WEB_DIR")
    if not value:
        return None
    folder = Path(value)
    if not (folder / "index.html").is_file():
        raise SystemExit(f"WEB_DIR ({value}) has no index.html: build the web page first")
    return folder
