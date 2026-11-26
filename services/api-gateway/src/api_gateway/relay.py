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
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "true-client-ip",
    # Who the person is, for the auth service: only the gateway says it (admin.py).
    "x-person",
}
# httpx gives the body already uncompressed and Response counts its length again; the server of
# the gateway writes its own date.
NOT_RETURNED = HOP_BY_HOP | {"content-length", "content-encoding", "date"}


def headers_to_send(request: Request) -> dict:
    """The headers of the browser that can go on. None starting with x-webauth-: Grafana trusts
    those, so only the gateway sets them. None starting with cf- either: Cloudflare writes there
    the address and the country of the visitor, which the services behind do not need."""
    headers = {}
    for name, value in request.headers.items():
        if name not in NOT_SENT and not name.startswith(("x-webauth-", "cf-")):
            headers[name] = value
    return headers


async def relay(client: httpx.AsyncClient, request: Request, headers: dict) -> Response:
    """Ask `client` for the same path, query, method and body as `request`, with `headers`."""
    # The client turns "/admin/../me" into "/me": with ".." a request could leave the part of the
    # service that the gateway passes on. No page of the auth service or Grafana needs it.
    if ".." in request.url.path:
        return problem(HTTPStatus.NOT_FOUND, "Not found.")
    url = request.url.path
    if request.url.query:
        url += "?" + request.url.query
    try:
        answer = await client.request(
            request.method, url, content=await request.body(), headers=headers
        )
    except httpx.HTTPError:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")

    response = Response(answer.content, status_code=answer.status_code)
    for name, value in answer.headers.multi_items():
        if name not in NOT_RETURNED:
            response.headers.append(name, value)
    return response
