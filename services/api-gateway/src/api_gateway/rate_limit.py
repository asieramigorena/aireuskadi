"""The limit of requests of the API, of the pages of the accounts and of Grafana: so many per
window of time (a minute by default) and per person, kept in memory.

The person is the LAST address of the header X-Forwarded-For. Cloudflare adds the address of the
client at the end of that header, after whatever the client wrote in it, and Tailscale Funnel
replaces the header with it: either way only the last one is true. An IPv6 address counts by its
network /64, which is what one home or one machine gets: all of it is one person. Without a tunnel
(on this machine) it is the address of the connection. In production only the tunnel reaches the
gateway, so nobody else can add to that header. The counts are kept in memory, only for the window
that is going on: a restart forgets them, which is enough for one gateway.
"""

import ipaddress
import time
from collections.abc import Callable
from http import HTTPStatus

from aireuskadi_http import problem
from fastapi import FastAPI, Request

WINDOW_SECONDS = 60
# What is counted: the API, the pages of the accounts and the admin panel. The page, its files and
# /health are not (a page is about twenty files, and the checks of the compose come every few seconds).
LIMITED_PATHS = ("/api/", "/admin", "/user")
# Security fix by Claude (audit 2026-11-26).
# Grafana is counted apart, with a limit five times bigger: a dashboard asks for dozens of files and
# one query per panel, and each request asks the auth service who the cookie is.
GRAFANA_PATH = "/grafana"
GRAFANA_TIMES = 5


class RateLimit:
    """`limit` requests per person in each window of `window` seconds (a minute by default)."""

    def __init__(
        self, limit: int, clock: Callable[[], float] = time.time, window: int = WINDOW_SECONDS
    ):
        self.limit = limit
        self.clock = clock
        self.window = window
        self.current: int | None = None
        self.counts: dict[str, int] = {}

    def allows(self, person: str) -> bool:
        """Counts one request of `person` and says whether it is within the limit of the window."""
        current = int(self.clock() // self.window)
        if current != self.current:
            # A new window: every count starts again, so the counts never grow beyond one window.
            self.current = current
            self.counts = {}
        self.counts[person] = self.counts.get(person, 0) + 1
        return self.counts[person] <= self.limit


def person_of(request: Request) -> str:
    """The address of the client: the last one of X-Forwarded-For, or the one of the connection.
    The header can come more than once; it is read as one list, like the tunnel reads it."""
    # Security fix by Claude (audit 2026-11-26): the last address, and IPv6 by its network /64.
    forwarded = ",".join(request.headers.getlist("x-forwarded-for"))
    last = forwarded.split(",")[-1].strip()
    address = last or (request.client.host if request.client else "")
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 6 and ip.ipv4_mapped:
        # An IPv4 address written as IPv6 (::ffff:1.2.3.4): the IPv4 one.
        return str(ip.ipv4_mapped)
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return address


def install_rate_limit(app: FastAPI, rate_limit: RateLimit) -> None:
    app.state.rate_limit = rate_limit
    grafana_limit = RateLimit(rate_limit.limit * GRAFANA_TIMES, rate_limit.clock, rate_limit.window)

    @app.middleware("http")
    async def limit(request: Request, call_next):
        path = request.url.path
        if path.startswith(GRAFANA_PATH):
            allowed = grafana_limit.allows(person_of(request))
        elif path.startswith(LIMITED_PATHS):
            allowed = rate_limit.allows(person_of(request))
        else:
            allowed = True
        if not allowed:
            response = problem(
                HTTPStatus.TOO_MANY_REQUESTS, "Too many requests: try again in a minute."
            )
            response.headers["Retry-After"] = str(WINDOW_SECONDS)
            return response
        return await call_next(request)
