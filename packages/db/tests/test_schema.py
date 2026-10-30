"""create_all() against a real PostgreSQL + PostGIS.

Skipped unless DATABASE_URL points to a database, e.g. the one of the local compose.
"""

import os

import pytest
from aireuskadi_db import SCHEMA, Base, create_all
from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")


def test_creates_the_tables_and_the_view_and_can_run_twice():
    engine = create_engine(URL)

    create_all(engine)
    create_all(engine)

    with engine.connect() as conn:
        tables = set(
            conn.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
                {"s": SCHEMA},
            )
        )
        views = set(
            conn.scalars(
                text("SELECT matviewname FROM pg_matviews WHERE schemaname = :s"), {"s": SCHEMA}
            )
        )
    assert {t.name for t in Base.metadata.sorted_tables} <= tables
    assert views == {"unit_indicator"}


def test_the_view_accepts_a_concurrent_refresh_right_after_creation():
    engine = create_engine(URL)
    create_all(engine)

    # CONCURRENTLY cannot run inside a transaction block.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {SCHEMA}.unit_indicator"))
