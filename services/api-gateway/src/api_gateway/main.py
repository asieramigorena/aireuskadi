"""Gateway entry point: puts the application together. The routes of the API are in routes.py,
the admin pages in admin.py, Grafana in grafana.py and the web page in web.py."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import redis.asyncio as redis
from aireuskadi_http import install_problem_documents, install_request_log
from aireuskadi_logger import configure_logging
from fastapi import FastAPI

from api_gateway import admin, grafana, routes
from api_gateway import insight as insight_routes
from api_gateway.cache import Cache
from api_gateway.insight import INSIGHT_PREFIX
from api_gateway.openapi import install_docs
from api_gateway.rate_limit import RateLimit, install_rate_limit
from api_gateway.web import web_router

PREFIX = "/api/v1"
# A page of the map makes about six calls when it opens, and a few more each time the zoom, the
# pollutant or the year changes: 120 a minute is far more than a person needs, and stops a script.
REQUESTS_PER_MINUTE = 120
# Sign-ups per person and hour (/user/signup): enough for a person, slow for a script.
SIGN_UPS_PER_HOUR = 3


def create_app(
    emissions: httpx.AsyncClient,
    *,
    air_quality: httpx.AsyncClient,
    cache: Cache | None = None,
    docs: bool = False,
    web_dir: Path | None = None,
    auth_client: httpx.AsyncClient | None = None,
    grafana_client: httpx.AsyncClient | None = None,
    rate_limit: RateLimit | None = None,
    insight: httpx.AsyncClient | None = None,
) -> FastAPI:
    """`emissions` and `air_quality` are the clients of the two services of the API, and
    `cache` the one of Redis (none: every question goes to the service). `docs` adds /docs
    and /openapi.json (openapi.py): the page loads its scripts from another site, so only if
    asked. `web_dir` is the folder of the compiled web page; without it the gateway publishes
    only the API (in development the page comes from Vite).
    `auth_client` is the client of the auth service, which makes the admin pages: without it
    /admin does not exist. With `grafana_client` too, admins see Grafana at /grafana/.
    `rate_limit` is how many requests a person can make each minute (none: no limit).
    `insight` is the client of the insight service (the questions to a language model): without it
    the questions do not exist."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await emissions.aclose()
        await air_quality.aclose()
        if auth_client:
            await auth_client.aclose()
        if grafana_client:
            await grafana_client.aclose()
        if insight:
            await insight.aclose()
        if cache:
            await cache.redis.aclose()

    app = FastAPI(
        title="AirEuskadi API Gateway",
        # The documentation is made by openapi.py (install_docs below), not by FastAPI.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
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
    app.state.cache = cache
    install_problem_documents(app)
    # Before the request log, so that the log sees the requests that the limit stops (a 429).
    if rate_limit:
        install_rate_limit(app, rate_limit)
    # The checks of the compose come every few seconds: they are only in the log at DEBUG.
    install_request_log(app, "api_gateway.access", quiet_paths=(routes.HEALTH_PATH,))
    app.include_router(routes.health)
    app.include_router(routes.router, prefix=PREFIX)
    if insight:
        app.state.insight = insight
        app.state.insight_cache = Cache(cache.redis, prefix=INSIGHT_PREFIX) if cache else None
        app.include_router(insight_routes.router, prefix=PREFIX)
    # The description of the routes is the list of what can be probed: only when asked.
    if docs:
        install_docs(app, PREFIX)
    if auth_client:
        app.state.auth = auth_client
        app.state.signup_limit = RateLimit(limit=SIGN_UPS_PER_HOUR, window=3600)
        app.include_router(admin.router)
        if grafana_client:
            app.state.grafana = grafana_client
            app.include_router(grafana.router)
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


def cache_from_env() -> Cache | None:
    """Redis at REDIS_URL, or no cache. It waits half a second at most: a Redis that does not
    answer must not make every request slow (the request then goes to the service)."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    return Cache(redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5))


def app_from_env() -> FastAPI:
    """Build the application from EMISSIONS_URL, AIR_QUALITY_URL, AUTH_URL and GRAFANA_URL (each
    with the name of the service in the compose as default) and WEB_DIR. It is what the
    container runs: uvicorn finds it by name in the CMD of gateway.Dockerfile (--factory), so no
    Python code calls it."""
    configure_logging("api_gateway", uvicorn=True)
    emissions = service_client("EMISSIONS_URL", "http://emissions-service:8000")
    air_quality = service_client("AIR_QUALITY_URL", "http://air-quality-service:8000")
    docs = os.environ.get("DOCS_ENABLED", "").lower() in ("1", "true")
    return create_app(
        emissions,
        air_quality=air_quality,
        cache=cache_from_env(),
        docs=docs,
        web_dir=web_dir_from_env(),
        auth_client=service_client("AUTH_URL", "http://auth-service:8000"),
        grafana_client=httpx.AsyncClient(
            base_url=os.environ.get("GRAFANA_URL", "http://grafana:3000"),
            # A dashboard can ask Loki or Prometheus for a long time.
            timeout=httpx.Timeout(30.0, connect=3.0),
            follow_redirects=False,
        ),
        rate_limit=RateLimit(limit=REQUESTS_PER_MINUTE),
        insight=httpx.AsyncClient(
            base_url=os.environ.get("INSIGHT_URL", "http://insight-service:8000"),
            # The insight service gives up on the language model after 20 s.
            timeout=httpx.Timeout(25.0, connect=3.0),
            follow_redirects=False,
        ),
    )


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
