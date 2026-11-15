"""The accounts: the login form, the JWT in a cookie, the logout, the page where an admin makes
other accounts admins, and /me (who the cookie is), which the gateway asks before Grafana.

Written like auth.py of the course example (FastAPI-TODO-Dual-Login-JWT): the JWT says who the user
is with its id (`sub`) and when it ends (`exp`), and is signed with JWT_SECRET (HS256). On every
request the user is read again from the database, so a deleted or demoted account loses its access
at once. The JWT goes in an HttpOnly cookie, which the JavaScript of a page cannot read.
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated

import jwt
from aireuskadi_db.accounts import USERNAME, clean_username, hash_password, verify_password
from aireuskadi_http import problem
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from auth_service.admin_pages import HEADERS, login_page, users_page
from auth_service.texts import with_language

logger = logging.getLogger("auth_service")

router = APIRouter(include_in_schema=False)

COOKIE = "aireuskadi_session"
HOURS = 8
# After 5 failed logins of the same name in 15 minutes, that name is refused until they are older.
MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
# The hash that an unknown name is checked against: made once, when the service starts.
DUMMY_HASH = hash_password("not the password of anyone")


def create_access_token(user_id: int, secret: str) -> str:
    expire = datetime.now(UTC) + timedelta(hours=HOURS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, secret, algorithm="HS256")


def current_user(request: Request):
    """The user of the cookie, or None if there is no cookie, it is not valid or has expired, or
    the account no longer exists."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    payload = read_token(request, token)
    if payload is None or (payload["sub"], payload["exp"]) in request.app.state.logged_out:
        return None
    return request.app.state.accounts.find(payload["sub"])


def read_token(request: Request, token: str) -> dict | None:
    """What the token says (`sub` as a number), if we signed it and it has not expired; else
    None."""
    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        payload["sub"] = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
    return payload


def current_admin(request: Request):
    """The user of the cookie if it is an admin, else None."""
    user = current_user(request)
    if user and user.is_admin:
        return user
    return None


def from_this_site(request: Request) -> bool:
    """Security fix by Claude (audit 2026-11-15): browsers say where a form was sent from
    (Sec-Fetch-Site). A form of another site cannot log someone in or out here. Without the
    header (an old browser, a test) it is let through: SameSite=Strict still protects the cookie."""
    return request.headers.get("sec-fetch-site") in (None, "same-origin", "none")


def redirect(url: str) -> RedirectResponse:
    """A 303 to `url`, with the same headers as the pages (not kept, no referrer)."""
    # Security fix by Claude (audit 2026-11-15): the headers of the pages on the redirects too.
    return RedirectResponse(url, status_code=303, headers=HEADERS)


def recent_failures(failures: dict, username: str) -> list[float]:
    """The moments of the failed logins of this name within the window."""
    now = time.monotonic()
    return [moment for moment in failures.get(username, []) if now - moment < WINDOW_SECONDS]


@router.get("/admin")
def admin_page(request: Request, error: str | None = None):
    return login_page(request, "wrong" if error is not None else None, current_user(request))


@router.post("/admin/login")
def login(request: Request, username: Annotated[str, Form()], password: Annotated[str, Form()]):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, "This form can only be sent from this site.")
    username = clean_username(username)
    accounts = request.app.state.accounts
    failures = request.app.state.failures

    recent = recent_failures(failures, username)
    if len(recent) >= MAX_FAILURES:
        logger.warning("login refused: too many failures")
        # A person sees the login page with the reason in their language, not a JSON document.
        page = login_page(request, "too_many", None)
        page.status_code = HTTPStatus.TOO_MANY_REQUESTS
        return page

    # Only the failures of real accounts are remembered, so the list never grows beyond them.
    if not USERNAME.fullmatch(username) or accounts.find_by_name(username) is None:
        # Security fix by Claude (audit 2026-11-15): a bcrypt check all the same, so that a name
        # that does not exist does not answer faster. (Accepted: after 5 failures a real name gets
        # the 429 and an unknown one does not, so someone patient can still learn that a name
        # exists. Names are not secret; the limit per account and the bcrypt passwords of at
        # least 12 characters are what protect an account.)
        verify_password("not the password of anyone", DUMMY_HASH)
        return failed_login(request)
    # Counted before the password is checked (bcrypt is slow): many requests sent at the same
    # time cannot all get through.
    failures[username] = recent + [time.monotonic()]

    user = accounts.authenticate(username, password)
    if user is None:
        return failed_login(request)

    failures.pop(username, None)
    logger.info("login ok", extra={"username": user.username})
    response = redirect("/grafana/")
    response.set_cookie(
        COOKIE,
        create_access_token(user.id, request.app.state.jwt_secret),
        max_age=HOURS * 60 * 60,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


def failed_login(request: Request) -> RedirectResponse:
    # Without the name: it could be a password typed in the wrong box.
    logger.warning("login failed")
    return redirect(with_language("/admin?error=1", request))


@router.post("/admin/logout")
def logout(request: Request):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, "This form can only be sent from this site.")
    # Security fix by Claude (audit 2026-11-15): the token of the cookie stops working now, not
    # when it expires. What is remembered is what the token says (the account and when it
    # expires), not its text: the same token can be written in more than one way. Only a token
    # signed by us is remembered (anyone can send a logout with any cookie), and only until it
    # would have expired anyway, so the list never grows beyond the logins of the last 8 hours.
    logged_out = request.app.state.logged_out
    token = request.cookies.get(COOKIE)
    payload = read_token(request, token) if token else None
    if payload:
        logged_out.add((payload["sub"], payload["exp"]))
    now = time.time()
    for old in [old for old in logged_out if old[1] < now]:
        logged_out.discard(old)
    response = redirect(with_language("/admin", request))
    response.delete_cookie(COOKIE, httponly=True, secure=True, samesite="strict")
    return response


@router.get("/admin/users")
def users(request: Request):
    admin = current_admin(request)
    if admin is None:
        return redirect(with_language("/admin", request))
    return users_page(request, request.app.state.accounts.all(), admin)


@router.post("/admin/users/{user_id}/admin")
def change_admin(request: Request, user_id: int, is_admin: Annotated[str, Form()] = ""):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, "This form can only be sent from this site.")
    admin = current_admin(request)
    if admin is None:
        return redirect(with_language("/admin", request))
    # The form is checked after who sends it, so that someone who is not an admin learns nothing
    # from a 422.
    if is_admin not in ("true", "false"):
        return problem(HTTPStatus.BAD_REQUEST, "is_admin must be true or false.")
    if user_id == admin.id:
        return problem(HTTPStatus.BAD_REQUEST, "You cannot change your own admin.")
    accounts = request.app.state.accounts
    user = accounts.find(user_id)
    if user is None:
        return problem(HTTPStatus.NOT_FOUND, "There is no such account.")

    # Logged only if it really changed (the account may have been deleted a moment before).
    if not accounts.set_admin(user_id, is_admin == "true"):
        return problem(HTTPStatus.NOT_FOUND, "There is no such account.")
    logger.info(
        "admin changed",
        extra={"by": admin.username, "user": user.username, "is_admin": is_admin == "true"},
    )
    return redirect(with_language("/admin/users", request))


@router.get("/me")
def me(request: Request):
    """Who the cookie is. Only the gateway asks it (it is not passed on from the browser)."""
    user = current_user(request)
    if user is None:
        return problem(HTTPStatus.UNAUTHORIZED, "Not logged in.")
    return {"username": user.username, "is_admin": user.is_admin}
