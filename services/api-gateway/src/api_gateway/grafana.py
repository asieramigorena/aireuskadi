"""/grafana/: Grafana behind the gateway, only for admins.

Grafana runs in "auth proxy" mode: it has no login of its own and trusts the name in the header
X-WEBAUTH-USER. Only the gateway can reach Grafana (they share a network that nothing else is on),
and the gateway always sets that header itself, after asking the auth service who the cookie is.
The rest of the request goes to Grafana unchanged, except our cookie: the JWT never leaves the
gateway for Grafana.
"""

from http import HTTPStatus

import httpx
from aireuskadi_http import problem
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from api_gateway.admin import COOKIE, our_cookie
from api_gateway.relay import headers_to_send, relay

router = APIRouter(include_in_schema=False)


async def admin_name(request: Request) -> str | None:
    """The name of the admin of the cookie, as the auth service says (it reads the account every
    time, so a removed admin is out at once), or None."""
    cookie = our_cookie(request)
    if not cookie:
        return None
    answer = await request.app.state.auth.get("/me", headers=cookie)
    if answer.status_code != 200:
        return None
    try:
        user = answer.json()
        if user["is_admin"] is True:
            return user["username"]
    except (ValueError, KeyError, TypeError):
        pass  # not the answer of a working auth service: nobody
    return None


@router.api_route("/grafana/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def grafana(request: Request, path: str):
    try:
        name = await admin_name(request)
    except httpx.HTTPError:
        return problem(HTTPStatus.BAD_GATEWAY, "The service is not available.")
    if name is None:
        return RedirectResponse("/admin", status_code=303)

    headers = headers_to_send(request)
    # The cookies of Grafana go on; ours does not.
    cookies = [f"{key}={value}" for key, value in request.cookies.items() if key != COOKIE]
    if cookies:
        headers["cookie"] = "; ".join(cookies)
    headers["x-webauth-user"] = name
    response = await relay(request.app.state.grafana, request, headers)
    # Security fix by Claude (audit 2026-11-15): Grafana shares the site, so an answer of it could
    # set or replace our cookie; only the auth service sets that one.
    response.raw_headers = [
        (key, value)
        for key, value in response.raw_headers
        if not (key == b"set-cookie" and COOKIE.encode() in value)
    ]
    return response
