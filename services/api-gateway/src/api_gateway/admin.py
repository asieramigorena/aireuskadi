"""/user/... and /admin/...: the pages of the accounts (log in, sign up, log out) and the panel of
the admins are made by the auth service. The gateway passes the requests on with our cookie only,
and gives back the answer as it is: the HTML, the cookie that the login sets, the redirects.

It also says who the cookie is (session_name), for the questions to the language model.
"""

from http import HTTPStatus

import httpx
from aireuskadi_http import problem
from fastapi import APIRouter, Request

from api_gateway.rate_limit import person_of
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


async def session_name(request: Request) -> str | None:
    """The name of the account of the cookie, as the auth service says (it reads the account
    every time, so a deleted one is out at once), or None: no cookie, a bad one, or no service."""
    cookie = our_cookie(request)
    auth = getattr(request.app.state, "auth", None)
    if not cookie or auth is None:
        return None
    try:
        answer = await auth.get("/me", headers=cookie)
        if answer.status_code == 200:
            name = answer.json()["username"]
            if isinstance(name, str):
                return name
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        pass  # not the answer of a working auth service: nobody
    return None


# /user and /admin, and everything under them (/user/login, /user/signup, /admin/users/3/admin...).
@router.api_route("/user", methods=["GET", "POST"])
@router.api_route("/user/{path:path}", methods=["GET", "POST"])
@router.api_route("/admin", methods=["GET", "POST"])
@router.api_route("/admin/{path:path}", methods=["GET", "POST"])
async def accounts(request: Request):
    # A few sign-ups per person and hour: a script must not make accounts by the thousand, nor try
    # names to learn which exist.
    signing_up = request.method == "POST" and request.url.path == "/user/signup"
    if signing_up and not request.app.state.signup_limit.allows(person_of(request)):
        return problem(HTTPStatus.TOO_MANY_REQUESTS, "Too many sign-ups: try again later.")
    headers = headers_to_send(request)
    headers.update(our_cookie(request))
    # Who the person is (the address that the tunnel says): the auth service counts the failed
    # logins per person and name, so that nobody can lock someone else's account.
    headers["x-person"] = person_of(request)
    return await relay(request.app.state.auth, request, headers)
