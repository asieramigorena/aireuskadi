"""Create the ``core`` schema, its tables and the ``unit_indicator`` view.

Used instead of migrations while the model is still changing: it only creates what is
missing and never alters or drops existing tables. To apply a change to an existing
table, recreate the database (``docker compose down -v``) and run it again.

Command line: ``aireuskadi-db-init`` reads the database URL from ``DATABASE_URL``.
"""

import os
import sys

from sqlalchemy import Engine, create_engine, text

from aireuskadi_db.base import SCHEMA, Base
from aireuskadi_db.views import UNIT_INDICATOR_DDL


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
    create_all(create_engine(url))
    print(f"Schema {SCHEMA} is ready")
