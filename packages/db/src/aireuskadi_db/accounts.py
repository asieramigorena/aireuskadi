"""The accounts of the site (auth.app_user): add one, check its password, make it an admin.

Used by the command of the owner (admin_cli.py) and by the auth service. The password is kept as a
bcrypt hash: the password itself is never stored and cannot be read back.
"""

import re

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from aireuskadi_db.models import AppUser

# Lower case letters, digits, "_", "." and "-": a name that Grafana and a URL keep as it is.
USERNAME = re.compile(r"[a-z0-9_.-]{3,40}")
MIN_PASSWORD = 5
# bcrypt reads at most 72 bytes of a password and refuses a longer one.
MAX_PASSWORD_BYTES = 72


def clean_username(name: str) -> str:
    """The name as it is kept: without spaces around it and in lower case."""
    return name.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# The hash that a login without a usable account is checked against: made once, at import.
DUMMY_HASH = hash_password("not the password of anyone")


class Accounts:
    """The accounts, read and written with `sessions` (a sessionmaker with
    expire_on_commit=False, so that a user can be used after its session is closed)."""

    def __init__(self, sessions: sessionmaker):
        self.sessions = sessions

    def add(self, username: str, password: str) -> AppUser:
        username = clean_username(username)
        if not USERNAME.fullmatch(username):
            raise ValueError("The name must have 3 to 40 letters, digits, '_', '.' or '-'")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"The password must have at least {MIN_PASSWORD} characters")
        if len(password.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"The password must have at most {MAX_PASSWORD_BYTES} bytes")
        if self.find_by_name(username):
            raise ValueError(f"There is already an account called {username}")
        user = AppUser(username=username, hashed_password=hash_password(password))
        with self.sessions() as session:
            session.add(user)
            try:
                session.commit()
            except IntegrityError:
                # Two adds of the same name at the same moment: the table refuses the second. A
                # clear error, not a traceback.
                raise ValueError(f"There is already an account called {username}") from None
        return user

    def sign_up(self, username: str, password: str) -> AppUser | None:
        """A new account from the sign-up page of the site, or None if it cannot be made (the name is
        taken or breaks the rules, the password is too short or too long). One answer for all of
        them: the page must not say which names exist.

        Only the name and the password are written: the role of the auth service may insert those
        two columns and nothing else, so `is_admin` takes its default, false. An admin is made with
        `aireuskadi-admin promote` (or by another admin)."""
        username = clean_username(username)
        too_long = len(password.encode()) > MAX_PASSWORD_BYTES
        if not USERNAME.fullmatch(username) or len(password) < MIN_PASSWORD or too_long:
            return None
        # Written by hand: the model would add `is_admin = false` itself, and that column is not
        # granted to the role of the auth service.
        new = text(
            "INSERT INTO auth.app_user (username, hashed_password) VALUES (:name, :hash) RETURNING id"
        )
        with self.sessions() as session:
            try:
                values = {"name": username, "hash": hash_password(password)}
                user_id = session.execute(new, values).scalar_one()
                session.commit()
            except IntegrityError:
                return None  # the name is taken
        return self.find(user_id)

    def find(self, user_id: int) -> AppUser | None:
        with self.sessions() as session:
            return session.get(AppUser, user_id)

    def find_by_name(self, username: str) -> AppUser | None:
        with self.sessions() as session:
            query = select(AppUser).where(AppUser.username == clean_username(username))
            return session.scalars(query).first()

    def authenticate(self, username: str, password: str) -> AppUser | None:
        """The user if the password is right, else None."""
        user = self.find_by_name(username)
        usable = (
            user is not None
            and user.hashed_password
            and len(password.encode()) <= MAX_PASSWORD_BYTES
        )
        if not usable:
            # Security fix by Claude (audit 2026-11-25): the slow bcrypt check runs all the same
            # (an unknown name, an account without password, a password that bcrypt cannot read),
            # so that how long a login takes says nothing about which accounts exist.
            verify_password("not the password of anyone", DUMMY_HASH)
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def set_admin(self, user_id: int, is_admin: bool) -> bool:
        """False if there is no such account (it may have been deleted a moment before)."""
        with self.sessions() as session:
            user = session.get(AppUser, user_id)
            if user is None:
                return False
            user.is_admin = is_admin
            session.commit()
            return True

    def delete(self, user_id: int) -> None:
        with self.sessions() as session:
            user = session.get(AppUser, user_id)
            if user:
                session.delete(user)
                session.commit()

    def all(self) -> list[AppUser]:
        with self.sessions() as session:
            return list(session.scalars(select(AppUser).order_by(AppUser.username)))
