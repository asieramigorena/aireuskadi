"""The accounts of the site (auth.app_user): add one, check its password, make it an admin.

Used by the command of the owner (admin_cli.py) and by the auth service. The password is kept as a
bcrypt hash, as in the course (there with passlib, here with bcrypt itself): the password is never
stored and cannot be read back.
"""

import re

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from aireuskadi_db.models import AppUser

# Lower case letters, digits, "_", "." and "-": a name that Grafana and a URL keep as it is.
USERNAME = re.compile(r"[a-z0-9_.-]{3,40}")
MIN_PASSWORD = 12
# bcrypt reads at most 72 bytes of a password and refuses a longer one.
MAX_PASSWORD_BYTES = 72


def clean_username(name: str) -> str:
    """The name as it is kept: without spaces around it and in lower case."""
    return name.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


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

    def find(self, user_id: int) -> AppUser | None:
        with self.sessions() as session:
            return session.get(AppUser, user_id)

    def find_by_name(self, username: str) -> AppUser | None:
        with self.sessions() as session:
            query = select(AppUser).where(AppUser.username == clean_username(username))
            return session.scalars(query).first()

    def authenticate(self, username: str, password: str) -> AppUser | None:
        """The user if the password is right, else None (as `authenticate_user` of the course)."""
        user = self.find_by_name(username)
        if not user or not user.hashed_password:
            return None
        if len(password.encode()) > MAX_PASSWORD_BYTES:
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
