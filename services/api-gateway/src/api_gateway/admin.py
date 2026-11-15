"""/admin/...: the pages of the accounts (login, logout, who is an admin) are made by the auth
service. The gateway passes the requests on with our cookie only, and gives back the answer as it
is: the HTML, the cookie that the login sets, the redirects.
"""

from fastapi import APIRouter, Request

from api_gateway.relay import headers_to_send, relay

router = APIRouter(include_in_schema=False)

# The cookie with the JWT, set by the auth service at the login.
COOKIE = "aireuskadi_session"


def our_cookie(request: Request) -> dict:
    """The Cookie header with only our cookie, or nothing if the browser has none."""
    value = request.cookies.get(COOKIE)
    if value is None:
        return {}
    return {"cookie": f"{COOKIE}={value}"}


# /admin and everything under it (/admin/login, /admin/users/3/admin...).
@router.api_route("/admin", methods=["GET", "POST"])
@router.api_route("/admin/{path:path}", methods=["GET", "POST"])
async def admin(request: Request):
    headers = headers_to_send(request)
    headers.update(our_cookie(request))
    return await relay(request.app.state.auth, request, headers)
