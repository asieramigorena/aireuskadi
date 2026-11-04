"""Plugin of pytest: the tests never use the database of the application.

They create rows and break constraints on purpose. Doing that in the database that holds the real
data left rows behind, and filled the log of PostgreSQL (and so the error panels of Grafana) with
errors that were expected. Roles are the exception: they belong to the whole server, not to a
database, so a test that creates one has to drop it itself.

So, before anything runs, `DATABASE_URL` is pointed to a database of its own on the same server,
`<name>_test`, which is created the first time. Only the process of pytest sees the change: the
URL that the application uses (the `.env` file) is not touched. Without `DATABASE_URL` nothing
happens and the tests of the database are skipped, as they are in the CI.

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


def prepare(admin, name):
    """Create the database of the tests if it is missing and set its log level.

    Several pytest sessions can start at the same time. They all find the database missing, and
    the ones that lose the race get an error of PostgreSQL ("already exists", "template busy",
    "tuple concurrently updated"). Every step can be repeated, so the session looks again."""
    for attempt in range(ATTEMPTS):
        try:
            with admin.connect() as conn:
                if not conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
                ):
                    conn.execute(text(f'CREATE DATABASE "{name}"'))
                # The errors that the tests provoke on purpose do not go to the log of the
                # server, where they would show up as errors of the application. A failure of
                # the server itself (FATAL) still does.
                conn.execute(text(f'ALTER DATABASE "{name}" SET log_min_messages = fatal'))
            return
        except OperationalError:
            raise  # the server is down: waiting does not help
        except DBAPIError:
            if attempt == ATTEMPTS - 1:
                raise
        time.sleep(0.2)


def pytest_configure(config):
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    real = make_url(url)
    if not real.database or real.database.endswith(SUFFIX):
        return  # already a database of the tests (or no database name to derive one from)
    name = real.database + SUFFIX

    admin = create_engine(real, isolation_level="AUTOCOMMIT")
    try:
        prepare(admin, name)
    except OperationalError:
        # The server is down or refuses the connection. Without DATABASE_URL the tests of the
        # database are skipped, and so they are now, instead of the whole session aborting or
        # the tests running against the database of the application.
        del os.environ["DATABASE_URL"]
        config.stash_server_unreachable = True
        return
    finally:
        admin.dispose()

    os.environ["DATABASE_URL"] = real.set(database=name).render_as_string(hide_password=False)
    config.stash_test_database = name


def pytest_report_header(config):
    if getattr(config, "stash_server_unreachable", False):
        return (
            "database of the tests: cannot reach the server, the tests of the database are skipped"
        )
    name = getattr(config, "stash_test_database", None)
    if name:
        return f"database of the tests: {name} (the one of the application is not used)"
    return None
