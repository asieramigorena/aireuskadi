"""Plugin of pytest: the tests never use the database of the application.

They create rows and break constraints on purpose, so they get a database of their own on the same
server, `<name>_test`, made the first time. Only the process of pytest sees the change: the .env
file is not touched. Without DATABASE_URL, or if the server cannot be reached, the tests of the
database are skipped.

The root pyproject.toml loads it for every run (`addopts = "-p testing"`).
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ALREADY_EXISTS = "42P04"  # what PostgreSQL says when another session made the database first


def pytest_configure(config):
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    real = make_url(url)
    if not real.database:
        # The server would take its default database, which can be the one of the application.
        del os.environ["DATABASE_URL"]
        return
    if real.database.endswith("_test"):
        return
    name = real.database + "_test"
    admin = create_engine(real, isolation_level="AUTOCOMMIT")

    # 1. Connect. If this fails the server is down or unreachable: skip the database tests.
    try:
        conn = admin.connect()
    except DBAPIError:
        del os.environ["DATABASE_URL"]
        admin.dispose()
        return

    # 2. Prepare the database of the tests. An error here is a real problem: it is raised.
    with conn:
        # The expected errors of this session do not go to the log of the server (and so to the
        # error panels of Grafana).
        conn.execute(text("SET log_min_messages = fatal"))
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}):
            try:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
            except DBAPIError as error:
                if getattr(error.orig, "sqlstate", None) != ALREADY_EXISTS:
                    raise
        # The errors that the tests cause on purpose do not go to the log of the server either.
        conn.execute(text(f'ALTER DATABASE "{name}" SET log_min_messages = fatal'))
    admin.dispose()
    os.environ["DATABASE_URL"] = real.set(database=name).render_as_string(hide_password=False)
