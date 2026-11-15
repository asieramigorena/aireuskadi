"""migrate(): the schema is made and changed by the migrations of Alembic (aireuskadi_db/migrations).

Each test has an empty database of its own on the same server, made and dropped here: what is
tested is what happens to a database that is new, or that was made before the migrations existed.
Skipped unless DATABASE_URL is set.
"""

import os

import pytest
from aireuskadi_db import SCHEMA, Base, Territory, migrate
from aireuskadi_db.schema import include_object
from aireuskadi_db.views import UNIT_INDICATOR_DDL
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")

HEAD = "0002"


@pytest.fixture
def empty_engine():
    url = make_url(URL)
    name = f"{url.database}_migrations"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(url.set(database=name))
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def version(engine):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT version_num FROM alembic_version"))


def test_an_empty_database_gets_every_table_and_the_view_already_filled(empty_engine):
    migrate(empty_engine)

    with empty_engine.connect() as conn:
        tables = set(
            conn.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
                {"s": SCHEMA},
            )
        )
        populated = conn.scalar(
            text("SELECT ispopulated FROM pg_matviews WHERE matviewname = 'unit_indicator'")
        )
    assert {table.name for table in Base.metadata.sorted_tables} <= tables
    # REFRESH ... CONCURRENTLY, which the worker uses, is refused on a view never filled.
    assert populated is True
    assert version(empty_engine) == HEAD


def test_it_can_run_again_and_changes_nothing(empty_engine):
    migrate(empty_engine)
    with Session(empty_engine) as session:
        session.add(Territory(code="99", name="Kept"))
        session.commit()

    migrate(empty_engine)

    assert version(empty_engine) == HEAD
    with Session(empty_engine) as session:
        assert session.get(Territory, "99").name == "Kept"


def test_a_database_made_before_the_migrations_is_marked_and_not_made_again(empty_engine):
    # What create_all() used to do: the tables and the view, and no record of a version. Running
    # the first migration on it would fail (the tables are there); its rows must be kept.
    with empty_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        Base.metadata.create_all(conn)
        for statement in UNIT_INDICATOR_DDL.split(";"):
            if statement.strip():
                conn.execute(text(statement))
        conn.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.unit_indicator"))
    with Session(empty_engine) as session:
        session.add(Territory(code="99", name="From before"))
        session.commit()

    migrate(empty_engine)

    assert version(empty_engine) == HEAD
    with Session(empty_engine) as session:
        assert session.get(Territory, "99").name == "From before"


def test_the_migrations_make_exactly_what_the_models_say(empty_engine):
    # A model that changes without a migration (or a migration that does not match its model) is a
    # difference here: write the migration (alembic.ini says how).
    migrate(empty_engine)

    with empty_engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"include_schemas": True, "include_object": include_object}
        )
        differences = compare_metadata(context, Base.metadata)
    assert differences == []


def test_a_database_made_before_without_the_indexes_of_the_simplified_boundaries_gets_them(
    empty_engine,
):
    # geom_simplified was added by hand to the databases of before, without its spatial index.
    with empty_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        Base.metadata.create_all(conn)
        for statement in UNIT_INDICATOR_DDL.split(";"):
            if statement.strip():
                conn.execute(text(statement))
        for table in ("territory", "district", "municipality"):
            conn.execute(text(f"DROP INDEX {SCHEMA}.idx_{table}_geom_simplified"))

    migrate(empty_engine)

    with empty_engine.connect() as conn:
        indexes = set(
            conn.scalars(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :s"), {"s": SCHEMA}
            )
        )
    assert {
        f"idx_{t}_geom_simplified" for t in ("territory", "district", "municipality")
    } <= indexes
