"""The pages of everyone, under /user: log in, sign up, log out, and /user/me for the map.

No answer says which accounts exist: a failed login is the same for an unknown name and a wrong
password (same text, same time), the lock after 5 failures counts any name, and every refused
sign-up is one answer. (A sign-up has to refuse a taken name, so someone can still learn that a
name exists by trying to register it: the gateway allows 3 sign-ups per person per hour.)
"""

import logging
import time
from http import HTTPStatus
from typing import Annotated

from aireuskadi_db.accounts import clean_username
from aireuskadi_http import problem
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from auth_service.admin_pages import account_page, login_page, signup_page
from auth_service.session import (
    COOKIE,
    HOURS,
    MAX_FAILURES,
    create_access_token,
    current_user,
    from_this_site,
    read_token,
    recent_failures,
    redirect,
    remember_failure,
)
from auth_service.texts import with_language

logger = logging.getLogger("auth_service")

router = APIRouter(include_in_schema=False)

ONLY_THIS_SITE = "This form can only be sent from this site."


def logged_in(request: Request, user, url: str) -> RedirectResponse:
    """The answer of a good login or sign-up: the cookie with the JWT, and on to `url`."""
    response = redirect(with_language(url, request))
    response.set_cookie(
        COOKIE,
        create_access_token(user.id, request.app.state.jwt_secret),
        max_age=HOURS * 60 * 60,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


@router.get("/user")
def login_form(request: Request, error: str | None = None):
    """The login form, or, for someone already logged in, the page of their account."""
    user = current_user(request)
    if user is not None:
        return account_page(request, user)
    return login_page(request, "wrong" if error is not None else None, None)


@router.post("/user/login")
def login(request: Request, username: Annotated[str, Form()], password: Annotated[str, Form()]):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, ONLY_THIS_SITE)
    username = clean_username(username)[:64]
    failures = request.app.state.failures
    # The failures of this person (as the gateway says) with this name: someone who fails locks
    # only themselves, never the account for everyone else. Any name counts, real or not.
    who = (request.headers.get("x-person", "")[:64], username)

    recent = recent_failures(failures, who)
    if len(recent) >= MAX_FAILURES:
        logger.warning("login refused: too many failures")
        # A person sees the login page with the reason in their language, not a JSON document.
        page = login_page(request, "too_many", None)
        page.status_code = HTTPStatus.TOO_MANY_REQUESTS
        return page
    # Counted before the password is checked (bcrypt is slow), and for any name, real or not.
    remember_failure(failures, who, recent)

    # Accounts.authenticate takes the same time for an unknown name, a wrong password or a
    # password too long for bcrypt (Security fix by Claude, audits 2026-11-15 and 2026-11-25).
    user = request.app.state.accounts.authenticate(username, password)
    if user is None:
        # Without the name: it could be a password typed in the wrong box.
        logger.warning("login failed")
        return redirect(with_language("/user?error=1", request))

    failures.pop(who, None)
    logger.info("login ok", extra={"username": user.username})
    # An admin goes to the panel; anyone else back to the map.
    return logged_in(request, user, "/admin" if user.is_admin else "/")


@router.get("/user/signup")
def signup_form(request: Request):
    return signup_page(request, refused=False, user=current_user(request))


@router.post("/user/signup")
def signup(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    again: Annotated[str, Form()],
):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, ONLY_THIS_SITE)
    username = clean_username(username)
    user = None
    # The account of the admin of Grafana is made by the owner, never here.
    if password == again and username not in request.app.state.reserved_names:
        user = request.app.state.accounts.sign_up(username, password)
    if user is None:
        # One answer for every reason: the page must not say which names exist.
        logger.warning("sign-up refused")
        page = signup_page(request, refused=True)
        page.status_code = HTTPStatus.BAD_REQUEST
        return page
    logger.info("sign-up", extra={"username": user.username})
    return logged_in(request, user, "/")


@router.post("/user/logout")
def logout(request: Request):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, ONLY_THIS_SITE)
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
    response = redirect(with_language("/user", request))
    response.delete_cookie(COOKIE, httponly=True, secure=True, samesite="strict")
    return response


@router.get("/user/me")
def user_me(request: Request):
    """Whether someone is logged in, and who: for the page of the map. The same 401 for a missing,
    expired, revoked or forged cookie."""
    user = current_user(request)
    if user is None:
        return problem(HTTPStatus.UNAUTHORIZED, "Not logged in.")
    return {"username": user.username}
