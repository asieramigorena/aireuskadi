"""Passing a whole request on to a service behind the gateway (the auth service or Grafana) and
giving back its whole answer: status, body and headers.

Unlike routes.py (only GET, only named parameters, a JSON answer), the admin pages and Grafana send
forms and cookies and answer HTML, redirects and cookies, so almost everything goes through. What
never goes through is listed here.
Relay managed by Claude
"""

from http import HTTPStatus

import httpx
from aireuskadi_http import problem
from fastapi import Request, Response

# Headers about one connection, not about the request: they are never passed on.
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
# Also not sent: the cookies (each route says which ones go), and the headers about who the visitor
# is, which the browser can write and the service behind could believe.
NOT_SENT = HOP_BY_HOP | {
    "host",
    "cookie",
    "content-length",
    "x-real-ip",
    "forwarded",
    "true-client-ip",
    "x-client-ip",
    "client-ip",
    "x-cluster-client-ip",
    "x-original-forwarded-for",
    # Who the person is, for the auth service: only the gateway says it (admin.py).
    "x-person",
}
# Security fix by Claude (audit 2026-11-26): the headers of the tunnels and every x-forwarded-.
NOT_SENT_PREFIXES = ("x-webauth-", "x-forwarded-", "cf-", "tailscale-")
# httpx gives the body already uncompressed and Response counts its length again; the server of
# the gateway writes its own date.
NOT_RETURNED = HOP_BY_HOP | {"content-length", "content-encoding", "date"}


def headers_to_send(request: Request) -> dict:
    """The headers of the browser that can go on. None starting with x-webauth-: Grafana trusts
    those, so only the gateway sets them. None about who the visitor is or where they came from
    either: x-forwarded-* and those of the tunnels (cf-* of Cloudflare, tailscale-* of Tailscale),
    which the browser can write too and the services behind do not need."""
    headers = {}
    for name, value in request.headers.items():
        if name not in NOT_SENT and not name.startswith(NOT_SENT_PREFIXES):
            headers[name] = value
    return headers


async def relay(
    client: httpx.AsyncClient, request: Request, headers: dict, body: bytes | None = None
) -> Response:
    """Ask `client` for the same path, query, method and body as `request`, with `headers`. The
    body, if it was already read (admin.py reads it with a limit); else it is read here."""
    # The client turns "/admin/../me" into "/me": with ".." a request could leave the part of the
    # service that the gateway passes on. It also turns "/user/./signup" into "/user/signup", a
    # sign-up that the limit of admin.py did not see. No page of the auth service or Grafana needs
    # either. Security fix by Claude (audit 2026-11-26): the single dot.
    if ".." in request.url.path or "." in request.url.path.split("/"):
        return problem(HTTPStatus.NOT_FOUND, "Not found.")
    url = request.url.path
    if request.url.query:
        url += "?" + request.url.query
    if body is None:
        body = await request.body()
    try:
        answer = await client.request(request.method, url, content=body, headers=headers)
    except httpx.InvalidURL:
        # A path with a character that no URL can have (%00): no page has it.
        # Security fix by Claude (audit 2026-11-26).
        return problem(HTTPStatus.NOT_FOUND, "Not found.")
    except httpx.HTTPError:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")

    response = Response(answer.content, status_code=answer.status_code)
    for name, value in answer.headers.multi_items():
        if name not in NOT_RETURNED:
            response.headers.append(name, value)
    return response
