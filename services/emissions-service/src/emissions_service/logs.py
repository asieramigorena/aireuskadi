"""The request log: one record per request, with what the dashboards filter on.

The JSON format and its setup are in the aireuskadi-logger package. `configure_logging` switches off
the access line of uvicorn (`uvicorn=True`) because this record replaces it.
"""

import logging
import time

from fastapi import FastAPI, Request

from emissions_service.health import HEALTH_PATH

_access = logging.getLogger("emissions_service.access")


def install_request_log(app: FastAPI) -> None:
    """One record per request. The query string is not logged: it can carry what the client
    typed."""

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        started = time.perf_counter()
        status = 500  # what the record says if the route raises and there is no response
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            # The checks of the compose come every few seconds: they are only in the log at DEBUG.
            level = logging.DEBUG if request.url.path == HEALTH_PATH else logging.INFO
            _access.log(
                level,
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
