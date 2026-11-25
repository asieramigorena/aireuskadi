"""Fixtures. The accounts are a fake (FakeAccounts): the tests run without a database."""

import logging
import sys
from types import SimpleNamespace

import pytest
from aireuskadi_db.accounts import USERNAME
from auth_service.main import create_app
from auth_service.session import COOKIE, create_access_token
from fastapi.testclient import TestClient

JWT_SECRET = "x" * 32


class FakeAccounts:
    """The accounts in a dict, with the methods of aireuskadi_db.accounts.Accounts that the
    service uses. `add` can make an admin at once, which the real one cannot."""

    def __init__(self):
        self.users = {}
        self.last_id = 0

    def add(self, username, password, is_admin=False):
        self.last_id += 1
        user = SimpleNamespace(
            id=self.last_id,
            username=username.strip().lower(),
            password=password,
            is_admin=is_admin,
            email=None,
        )
        self.users[user.id] = user
        return user

    def sign_up(self, username, password):
        """Like Accounts.sign_up: None when the name is taken or breaks the rules."""
        username = username.strip().lower()
        if len(password) < 5 or not USERNAME.fullmatch(username) or self.find_by_name(username):
            return None
        return self.add(username, password)

    def find(self, user_id):
        return self.users.get(user_id)

    def find_by_name(self, username):
        for user in self.users.values():
            if user.username == username.strip().lower():
                return user
        return None

    def authenticate(self, username, password):
        user = self.find_by_name(username)
        if user and user.password == password:
            return user
        return None

    def set_admin(self, user_id, is_admin):
        if user_id not in self.users:
            return False
        self.users[user_id].is_admin = is_admin
        return True

    def delete(self, user_id):
        self.users.pop(user_id, None)

    def all(self):
        return sorted(self.users.values(), key=lambda user: user.username)


@pytest.fixture
def fake_accounts():
    return FakeAccounts()


@pytest.fixture
def admin_client(fake_accounts):
    """The service with the fake accounts. HTTPS, so that the client sends back the Secure
    cookie (the browser reaches the site through HTTPS)."""
    # "grafanaadmin" is the account named in GRAFANA_ADMIN_USER: nobody can sign up with it.
    app = create_app(fake_accounts, JWT_SECRET, reserved_names=("grafanaadmin",))
    with TestClient(app, base_url="https://testserver") as client:
        yield client


@pytest.fixture
def logged_in_as(admin_client, fake_accounts):
    """Add an account and give admin_client the cookie of that account, as after its login."""

    def log_in(username, is_admin):
        user = fake_accounts.add(username, "a-long-password-1", is_admin=is_admin)
        admin_client.cookies.set(COOKIE, create_access_token(user.id, JWT_SECRET))
        return admin_client

    return log_in


@pytest.fixture(autouse=True)
def keep_logging_state():
    """app_from_env sets up the logging (the root logger, uvicorn's, sys.excepthook): put it back
    after the test."""
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access"]
    saved = [(n, logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in names]
    level, hook = logging.getLogger().level, sys.excepthook
    yield
    for name, handlers, propagate in saved:
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate
    logging.getLogger().setLevel(level)
    sys.excepthook = hook
