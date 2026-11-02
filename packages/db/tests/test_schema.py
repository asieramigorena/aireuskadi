"""create_all() against a real PostgreSQL + PostGIS.

Skipped unless DATABASE_URL points to a database, e.g. the one of the local compose.
"""

import os

import pytest
from aireuskadi_db import SCHEMA, Base, IngestionRun, Pollutant, create_all
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")


@pytest.fixture
def engine():
    engine = create_engine(URL)
    create_all(engine)
    return engine


def test_creates_the_tables_and_the_view_and_can_run_twice(engine):
    create_all(engine)

    with engine.connect() as conn:
        tables = {
            tuple(row)
            for row in conn.execute(
                text("SELECT table_schema, table_name FROM information_schema.tables")
            )
        }
        views = set(
            conn.scalars(text("SELECT matviewname FROM pg_matviews WHERE schemaname = 'core'"))
        )
    assert {(t.schema, t.name) for t in Base.metadata.sorted_tables} <= tables
    assert views == {"unit_indicator"}


def test_the_view_accepts_a_concurrent_refresh_right_after_creation(engine):
    # CONCURRENTLY cannot run inside a transaction block.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {SCHEMA}.unit_indicator"))


def test_a_run_cannot_have_an_unknown_status(engine):
    with Session(engine) as session:
        session.add(IngestionRun(source="eprtr_air", status="halfway"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_an_eprtr_code_belongs_to_one_pollutant_but_measured_only_pollutants_have_none(engine):
    with Session(engine) as session:
        session.add_all(
            [
                Pollutant(code="T_NOX", name="Nitrogen oxides", eprtr_code="T30402"),
                Pollutant(code="T_NO2", name="Nitrogen dioxide"),  # only measured: no E-PRTR code
                Pollutant(code="T_SO2", name="Sulphur dioxide"),
            ]
        )
        session.flush()  # two pollutants without a code are fine

        session.add(Pollutant(code="T_OTHER", name="Duplicate", eprtr_code="T30402"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
