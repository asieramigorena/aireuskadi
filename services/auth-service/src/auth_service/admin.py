"""The panel of the admins (/admin): the accounts, the button to make or unmake an admin, and the
way to Grafana. And /me, which the gateway asks before it opens Grafana to someone.

Someone who is not an admin does not see the panel: without a session they are sent to the login,
with one the panel answers 404, as if it did not exist.
"""

import logging
from http import HTTPStatus
from typing import Annotated

from aireuskadi_http import problem
from fastapi import APIRouter, Form, Request

from auth_service.admin_pages import users_page
from auth_service.session import current_admin, current_user, from_this_site, redirect
from auth_service.texts import with_language

logger = logging.getLogger("auth_service")

router = APIRouter(include_in_schema=False)


def not_admin(request: Request):
    """The answer for someone who is not an admin: the login without a session; with one, a 404,
    as if the panel did not exist."""
    if current_user(request) is None:
        return redirect(with_language("/user", request))
    return problem(HTTPStatus.NOT_FOUND, "Not Found")


@router.get("/admin")
def panel(request: Request):
    """The panel of the admins: the accounts, the button to make an admin, and the way to Grafana."""
    admin = current_admin(request)
    if admin is None:
        return not_admin(request)
    return users_page(request, request.app.state.accounts.all(), admin)


@router.post("/admin/users/{user_id}/admin")
def change_admin(request: Request, user_id: int, is_admin: Annotated[str, Form()] = ""):
    if not from_this_site(request):
        return problem(HTTPStatus.FORBIDDEN, "This form can only be sent from this site.")
    admin = current_admin(request)
    if admin is None:
        return not_admin(request)
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
    return redirect(with_language("/admin", request))


@router.get("/me")
def me(request: Request):
    """Who the cookie is. Only the gateway asks it (it is not passed on from the browser)."""
    user = current_user(request)
    if user is None:
        return problem(HTTPStatus.UNAUTHORIZED, "Not logged in.")
    return {"username": user.username, "is_admin": user.is_admin}
