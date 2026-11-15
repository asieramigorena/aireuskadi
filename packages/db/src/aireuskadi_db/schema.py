"""Bring the database to the latest version, with the migrations of Alembic (``migrations/versions``):
the tables of ``core`` and ``auth``, their indexes and the ``unit_indicator`` view.

A change of the models is a new migration (``packages/db/alembic.ini`` says how to write one), so
that a database with data is changed and never recreated. A database made before the migrations
existed (with ``Base.metadata.create_all``) is marked as being at the first one.

Command line: ``aireuskadi-db-init`` reads the database URL from ``DATABASE_URL``. If
``POSTGRES_READER_USER`` and ``POSTGRES_READER_PASSWORD`` are set it also creates (or updates) the
read-only role of the services that only read, and with ``POSTGRES_AUTH_USER`` and
``POSTGRES_AUTH_PASSWORD`` the role of the auth service, see ``roles.py``. It always loads the WHO guideline
values (``who.py``) and refreshes the view that divides by them.
"""

import os
import sys

from alembic import command
from alembic.config import Config
from geoalchemy2 import alembic_helpers
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from aireuskadi_db.base import AUTH_SCHEMA, SCHEMA
from aireuskadi_db.roles import create_auth_role, create_reader_role
from aireuskadi_db.who import seed_who_guidelines

# The revision that a database made before the migrations already has: everything of it.
BASELINE = "0001"


def include_object(obj, name, type_, reflected, compare_to):
    """What Alembic compares with the models: only the tables of core and auth. PostGIS keeps
    tables of its own (spatial_ref_sys, the ones of the tiger geocoder) and a migration must never
    drop them."""
    if type_ == "table" and getattr(obj, "schema", None) not in (SCHEMA, AUTH_SCHEMA):
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


def migrate(engine: Engine) -> None:
    """Apply the migrations that the database does not have yet. Safe to run again."""
    config = Config()
    config.set_main_option("script_location", "aireuskadi_db:migrations")
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        if made_before_the_migrations(conn):
            command.stamp(config, BASELINE)
        command.upgrade(config, "head")


def made_before_the_migrations(conn) -> bool:
    """The tables of core are there, but there is no record of a version."""
    inspector = inspect(conn)
    return not inspector.has_table("alembic_version") and inspector.has_table(
        "municipality", schema=SCHEMA
    )


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set, e.g. postgresql+psycopg://user:password@host:5432/db")
    engine = create_engine(url)
    migrate(engine)
    print(f"Schema {SCHEMA} is ready")

    # The reference values of the WHO, and the view that divides by them.
    with Session(engine) as session, session.begin():
        seed_who_guidelines(session)
        session.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.unit_indicator"))
    print("WHO guidelines (2021) are loaded")

    # The read-only role of the services that only read. Both variables or neither: half of the
    # credentials is a mistake, and guessing the other half would be worse than stopping.
    user = os.environ.get("POSTGRES_READER_USER")
    password = os.environ.get("POSTGRES_READER_PASSWORD")
    if user or password:
        if not (user and password):
            sys.exit("Set both POSTGRES_READER_USER and POSTGRES_READER_PASSWORD, or neither")
        create_reader_role(engine, user, password)
        print(f"Role {user} is ready (it can only read)")

    # The role of the auth service, which reads the accounts. The same rule: both or neither.
    user = os.environ.get("POSTGRES_AUTH_USER")
    password = os.environ.get("POSTGRES_AUTH_PASSWORD")
    if user or password:
        if not (user and password):
            sys.exit("Set both POSTGRES_AUTH_USER and POSTGRES_AUTH_PASSWORD, or neither")
        create_auth_role(engine, user, password)
        print(f"Role {user} is ready (it reads the accounts)")
