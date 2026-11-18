"""The limit of requests of the API and of the admin pages: so many per minute and per person, like
`rateLimit({ windowMs: 60_000, limit: 100 })` of the course example (express-rate-limit).

The person is the address of the header X-Forwarded-For, which the tunnel (Tailscale Funnel) writes
itself with the address of the client: it replaces whatever the client sent. Without the tunnel (on
this machine) it is the address of the connection. In production only the tunnel reaches the
gateway, so nobody else can choose that header. The counts are kept in memory, only for the minute
that is going on: a restart forgets them, which is enough for one gateway.
"""

import time
from collections.abc import Callable
from http import HTTPStatus

from aireuskadi_http import problem
from fastapi import FastAPI, Request

WINDOW_SECONDS = 60
# What is counted: the API and the admin pages. The page, its files and /health are not (a page is
# about twenty files, and the checks of the compose come every few seconds).
LIMITED_PATHS = ("/api/", "/admin")


class RateLimit:
    def __init__(self, limit: int, clock: Callable[[], float] = time.time):
        self.limit = limit
        self.clock = clock
        self.minute: int | None = None
        self.counts: dict[str, int] = {}

    def allows(self, person: str) -> bool:
        """Counts one request of `person` and says whether it is within the limit of the minute."""
        minute = int(self.clock() // WINDOW_SECONDS)
        if minute != self.minute:
            # A new minute: every count starts again, so the counts never grow beyond one minute.
            self.minute = minute
            self.counts = {}
        self.counts[person] = self.counts.get(person, 0) + 1
        return self.counts[person] <= self.limit


def person_of(request: Request) -> str:
    """The address of the client: the one that the tunnel says, or the one of the connection."""
    return request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")


def install_rate_limit(app: FastAPI, rate_limit: RateLimit) -> None:
    app.state.rate_limit = rate_limit

    @app.middleware("http")
    async def limit(request: Request, call_next):
        if request.url.path.startswith(LIMITED_PATHS) and not rate_limit.allows(person_of(request)):
            response = problem(
                HTTPStatus.TOO_MANY_REQUESTS, "Too many requests: try again in a minute."
            )
            response.headers["Retry-After"] = str(WINDOW_SECONDS)
            return response
        return await call_next(request)
