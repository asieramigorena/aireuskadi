"""Create the ``core`` schema, its tables and the ``unit_indicator`` view.

Used instead of migrations while the model is still changing: it only creates what is
missing and never alters or drops existing tables. To apply a change to an existing
table, recreate the database (``docker compose down -v``) and run it again.

Command line: ``aireuskadi-db-init`` reads the database URL from ``DATABASE_URL``. If
``POSTGRES_READER_USER`` and ``POSTGRES_READER_PASSWORD`` are set it also creates (or updates) the
read-only role of the services that only read, see ``roles.py``. It always loads the WHO guideline
values (``who.py``) and refreshes the view that divides by them.
"""

import os
import sys

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from aireuskadi_db.base import SCHEMA, Base
from aireuskadi_db.roles import create_reader_role
from aireuskadi_db.views import UNIT_INDICATOR_DDL
from aireuskadi_db.who import seed_who_guidelines


def create_all(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        Base.metadata.create_all(conn)
        # One statement at a time: the DDL holds the view and its unique index.
        for statement in UNIT_INDICATOR_DDL.split(";"):
            if statement.strip():
                conn.execute(text(statement))
        # The view is created WITH NO DATA, and REFRESH ... CONCURRENTLY (used by the
        # worker) is rejected on a view that was never populated.
        populated = conn.scalar(
            text("SELECT ispopulated FROM pg_matviews WHERE schemaname = :s AND matviewname = :v"),
            {"s": SCHEMA, "v": "unit_indicator"},
        )
        if not populated:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.unit_indicator"))


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set, e.g. postgresql+psycopg://user:password@host:5432/db")
    engine = create_engine(url)
    create_all(engine)
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
