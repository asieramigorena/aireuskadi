"""The session of a person: the JWT in a cookie, who it is, and the memory of the failed logins.
Shared by the pages of everyone (user.py) and the panel of the admins (admin.py).

The JWT says who the user is with its id (`sub`) and when it ends (`exp`), and is signed with
JWT_SECRET (HS256). On every
request the user is read again from the database, so a deleted or demoted account loses its access
at once. The JWT goes in an HttpOnly cookie, which the JavaScript of a page cannot read.
"""

import time
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request
from fastapi.responses import RedirectResponse

from auth_service.admin_pages import HEADERS

# __Host-: the browser keeps it only with this name, for path / and over https, so that no other
# name under the domain can set or replace it. Security fix by Claude (audit 2026-11-26).
COOKIE = "__Host-aireuskadi_session"
HOURS = 8
# After 5 failed logins of the same person with the same name in 15 minutes, they are refused until
# the failures are older. Every name counts, real or not: a 429 that only real names got would say
# which accounts exist. Per person too: otherwise anyone could keep an admin out.
MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
# The names whose failures are remembered, at most: the oldest are forgotten first.
MAX_NAMES = 10_000


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


def recent_failures(failures: dict, who: tuple[str, str]) -> list[float]:
    """The moments of the failed logins of `who` (person, name) within the window."""
    now = time.monotonic()
    return [moment for moment in failures.get(who, []) if now - moment < WINDOW_SECONDS]


def remember_failure(failures: dict, who: tuple[str, str], recent: list[float]) -> None:
    """Adds a failure of `who` (person, name). The dict keeps the order in which names were last added, so
    when it is full the first one is the oldest and is forgotten."""
    failures.pop(who, None)
    failures[who] = recent + [time.monotonic()]
    while len(failures) > MAX_NAMES:
        del failures[next(iter(failures))]
