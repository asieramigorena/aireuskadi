"""Plugin of pytest: the tests never use the database of the application.

They create rows and break constraints on purpose. Doing that in the database that holds the real
data left rows behind, and filled the log of PostgreSQL (and so the error panels of Grafana) with
errors that were expected. Roles are the exception: they belong to the whole server, not to a
database, so a test that creates one has to drop it itself.

So, before anything runs, `DATABASE_URL` is pointed to a database of its own on the same server,
`<name>_test`, which is created the first time. Only the process of pytest sees the change: the
URL that the application uses (the `.env` file) is not touched. Without `DATABASE_URL` nothing
happens and the tests of the database are skipped, as they are in the CI. They are skipped too, with
the reason in the header of pytest, when the server cannot be connected to.

The root `pyproject.toml` loads it for every run (`pythonpath` and `addopts = "-p testing"`), so
the tests of every package use it. It is not a `conftest.py`: that one only reaches the tests under
its folder. It lives with the tests, not in `src`, so that it is not installed with the package.
"""

import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError

SUFFIX = "_test"
ATTEMPTS = 10

# What PostgreSQL answers to the sessions that lose the race to create the same database: it
# already exists, the template it is copied from is in use by the winner, "tuple concurrently
# updated", and the same name inserted twice in the catalog (unique violation).
RACE = {"42P04", "55006", "XX000", "23505"}


class CannotConnect(Exception):
    """The connection to the server could not be made: it is down or starting, the credentials are
    wrong, the network fails. Before the connection exists there is no SQLSTATE to tell these
    apart, and the tests that do not use the database can run in all of them."""


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def prepare(admin, name):
    """Create the database of the tests if it is missing and set its log level.

    Several pytest sessions can start at the same time. They all find the database missing, and
    the ones that lose the race get one of the errors of RACE, so every step can be repeated and
    the session looks again. What decides is where the error happens: while connecting it is
    CannotConnect (not retried), and once connected any error that is not of the race is raised
    at once, because waiting does not solve it."""
    quoted = quote(name)
    for attempt in range(ATTEMPTS):
        try:
            connection = admin.connect()
        except OperationalError as error:
            raise CannotConnect(str(error.orig).strip().partition("\n")[0]) from error
        with connection as conn:
            try:
                # The errors of the race are expected, and the log of the server feeds the error
                # panels of Grafana: this session does not write them there. Raised to pytest
                # all the same.
                conn.execute(text("SET log_min_messages = fatal"))
                if not conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
                ):
                    conn.execute(text(f"CREATE DATABASE {quoted}"))
                # The errors that the tests provoke on purpose do not go to the log of the
                # server, where they would show up as errors of the application. A failure of
                # the server itself (FATAL) still does.
                conn.execute(text(f"ALTER DATABASE {quoted} SET log_min_messages = fatal"))
                return
            except DBAPIError as error:
                if getattr(error.orig, "sqlstate", None) not in RACE or attempt == ATTEMPTS - 1:
                    raise
        time.sleep(0.2)


def pytest_configure(config):
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    real = make_url(url)
    if real.database and real.database.endswith(SUFFIX):
        return  # already a database of the tests
    if not real.database:
        # The server would take its default database, which can be the one of the application.
        del os.environ["DATABASE_URL"]
        config.test_database_header = (
            "database of the tests: DATABASE_URL has no database name, "
            "the tests of the database are skipped"
        )
        return
    name = real.database + SUFFIX

    admin = create_engine(real, isolation_level="AUTOCOMMIT")
    try:
        prepare(admin, name)
    except CannotConnect as error:
        # Without DATABASE_URL the tests of the database are skipped, and so they are now, instead
        # of the whole session aborting or the tests running against the application database.
        del os.environ["DATABASE_URL"]
        config.test_database_header = (
            f"database of the tests: cannot connect to the server, "
            f"the tests of the database are skipped ({error})"
        )
        return
    finally:
        admin.dispose()

    os.environ["DATABASE_URL"] = real.set(database=name).render_as_string(hide_password=False)
    config.test_database_header = (
        f"database of the tests: {name} (the one of the application is not used)"
    )


def pytest_report_header(config):
    return getattr(config, "test_database_header", None)
