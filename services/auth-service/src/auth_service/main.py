"""Auth service entry point: the accounts of the site (auth.app_user). The pages of everyone (log in,
sign up, log out) are in user.py, the panel of the admins in admin.py, the session in session.py.

It is the only service that reads the accounts. The browser reaches it through the gateway, which
passes /user/... and /admin/... on to it and asks /me before Grafana and the questions to the model.
"""

import os

from aireuskadi_db.accounts import Accounts
from aireuskadi_http import install_problem_documents, install_request_log
from aireuskadi_logger import configure_logging
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth_service import admin, user

HEALTH_PATH = "/health"


def create_app(accounts, jwt_secret: str, reserved_names: tuple[str, ...] = ()) -> FastAPI:
    """`accounts` is aireuskadi_db.accounts.Accounts (a fake in the tests), `jwt_secret` signs
    the JWT of the cookies, and `reserved_names` are names that nobody can sign up with (the
    account of the admin of Grafana, GRAFANA_ADMIN_USER)."""
    app = FastAPI(
        title="AirEuskadi Auth Service",
        # Nothing of it is public API: no OpenAPI document and no interactive pages.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.state.accounts = accounts
    app.state.jwt_secret = jwt_secret
    app.state.reserved_names = {name.strip().lower() for name in reserved_names if name.strip()}
    # The failed logins by name (session.py): every name, real or not, at most MAX_NAMES.
    app.state.failures = {}
    # The tokens of the logouts, which no longer open anything, as (account id, expiry). Kept in
    # memory: a restart forgets them (they still expire after 8 hours).
    app.state.logged_out = set()
    install_problem_documents(app)
    # The checks of the compose come every few seconds: they are only in the log at DEBUG.
    install_request_log(app, "auth_service.access", quiet_paths=(HEALTH_PATH,))
    app.include_router(user.router)
    app.include_router(admin.router)

    @app.get(HEALTH_PATH, include_in_schema=False)
    def health():
        return {"status": "ok"}

    return app


def app_from_env() -> FastAPI:
    """Build the application from AUTH_DATABASE_URL (the role of this service) and JWT_SECRET. It
    is what the container runs: uvicorn finds it by name in the CMD of auth.Dockerfile (--factory).
    A short secret stops the start: a JWT signed with it could be guessed."""
    configure_logging("auth_service", uvicorn=True)
    url = os.environ.get("AUTH_DATABASE_URL")
    if not url:
        raise SystemExit("AUTH_DATABASE_URL is not set (see .env.example)")
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32:
        raise SystemExit("JWT_SECRET must have at least 32 characters")
    # A small pool: the role of this service may open 5 connections at most.
    engine = create_engine(
        url, pool_size=2, max_overflow=2, pool_timeout=5, connect_args={"connect_timeout": 5}
    )
    # The account that is the full admin of Grafana is made by the owner: nobody can sign up as it.
    reserved = (os.environ.get("GRAFANA_ADMIN_USER", ""),)
    return create_app(Accounts(sessionmaker(engine, expire_on_commit=False)), secret, reserved)
