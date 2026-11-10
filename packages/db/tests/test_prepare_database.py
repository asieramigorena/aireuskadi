"""The plugin that creates the database of the tests: `prepare` and `pytest_configure`.

PostgreSQL cannot be made to answer "the template is busy" or "wrong password" when a test wants
it, so the connection is a fake that raises the errors the real one raised (the race was checked
with six real sessions in test_test_database.py). The errors are the ones of psycopg, wrapped by
SQLAlchemy as they are in real life.

What the plugin decides is where the failure happened, not which error it is: before the connection
exists there is no SQLSTATE and whatever went wrong (server down, starting, wrong password) means
"cannot connect"; after it, the errors of the race are retried and any other one is raised.
"""

import os
from contextlib import nullcontext
from types import SimpleNamespace

import psycopg.errors as pg
import pytest
import testing
from sqlalchemy.exc import IntegrityError, InternalError, OperationalError, ProgrammingError


class FakeConnection:
    def __init__(self, errors):
        self.errors = errors
        self.statements = []

    def scalar(self, *args, **kwargs):
        return None  # the database does not exist yet

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        if "CREATE DATABASE" in str(statement) and self.errors:
            raise self.errors.pop(0)


class FakeAdmin:
    """`connect_error` is raised by connect() itself, like a server that cannot be reached;
    `errors` are raised by the CREATE DATABASE of a connection that was made."""

    def __init__(self, *errors, connect_error=None):
        self.conn = FakeConnection(list(errors))
        self.connect_error = connect_error
        self.connections = 0
        self.disposed = False

    def connect(self):
        self.connections += 1
        if self.connect_error:
            raise self.connect_error
        return nullcontext(self.conn)

    def dispose(self):
        self.disposed = True


def wrapped(sqlalchemy_class, psycopg_error):
    return sqlalchemy_class("CREATE DATABASE", {}, psycopg_error)


BUSY = wrapped(OperationalError, pg.ObjectInUse("template1 is being accessed"))


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(testing.time, "sleep", lambda seconds: None)


# --- prepare: the connection is made -------------------------------------------------------


def test_a_busy_template_is_retried_until_it_is_free():
    # Raised by PostgreSQL when two sessions create a database at the same time. It is a subclass
    # of OperationalError, like a refused connection, and must not be taken for one.
    admin = FakeAdmin(BUSY, BUSY)

    testing.prepare(admin, "x_test")

    assert admin.connections == 3
    assert any("ALTER DATABASE" in s for s in admin.conn.statements)


@pytest.mark.parametrize(
    "error",
    [
        wrapped(ProgrammingError, pg.DuplicateDatabase("already exists")),
        wrapped(InternalError, pg.InternalError_("tuple concurrently updated")),
        # Two sessions insert the same name in the catalog of PostgreSQL at the same moment.
        wrapped(IntegrityError, pg.UniqueViolation("pg_database_datname_index")),
    ],
)
def test_the_other_errors_of_the_race_are_retried(error):
    admin = FakeAdmin(error)

    testing.prepare(admin, "x_test")

    assert admin.connections == 2


def test_an_error_that_is_not_part_of_the_race_is_raised_at_once():
    # Waiting does not give a user the privilege to create databases.
    admin = FakeAdmin(wrapped(ProgrammingError, pg.InsufficientPrivilege("permission denied")))

    with pytest.raises(ProgrammingError):
        testing.prepare(admin, "x_test")

    assert admin.connections == 1


def test_a_race_that_never_ends_is_raised_after_the_last_attempt_and_is_not_a_missing_server():
    admin = FakeAdmin(*[BUSY] * testing.ATTEMPTS)

    with pytest.raises(OperationalError) as raised:
        testing.prepare(admin, "x_test")

    assert not isinstance(raised.value, testing.CannotConnect)
    assert admin.connections == testing.ATTEMPTS


def test_the_name_is_quoted_in_the_sql():
    admin = FakeAdmin()

    testing.prepare(admin, 'x"; DROP DATABASE y; --')

    create = [s for s in admin.conn.statements if s.startswith("CREATE")]
    assert create == ['CREATE DATABASE "x""; DROP DATABASE y; --"']


def test_the_errors_of_the_race_never_reach_the_log_of_the_server():
    # They are expected, and the log of PostgreSQL feeds the error panels of Grafana. Every
    # connection silences its own session before it tries to create the database.
    silence = "SET log_min_messages = fatal"
    admin = FakeAdmin(BUSY)

    testing.prepare(admin, "x_test")

    assert admin.conn.statements == [
        silence,
        'CREATE DATABASE "x_test"',  # the one that fails
        silence,
        'CREATE DATABASE "x_test"',
        'ALTER DATABASE "x_test" SET log_min_messages = fatal',
    ]


# --- prepare: the connection cannot be made ------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        pg.OperationalError("connection failed: Connection refused"),
        pg.CannotConnectNow("the database system is starting up"),
        pg.OperationalError('FATAL: password authentication failed for user "u"'),
    ],
)
def test_whatever_stops_the_connection_is_a_missing_server_and_is_not_retried(reason):
    admin = FakeAdmin(connect_error=wrapped(OperationalError, reason))

    with pytest.raises(testing.CannotConnect) as raised:
        testing.prepare(admin, "x_test")

    assert admin.connections == 1
    assert str(reason).split("\n")[0] in str(raised.value)


# --- pytest_configure ----------------------------------------------------------------------


@pytest.fixture
def configure(monkeypatch):
    """Runs pytest_configure with a URL and a fake admin connection; returns (config, admin)."""

    def run(url, admin):
        if url is None:
            monkeypatch.delenv("DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setattr(testing, "create_engine", lambda *args, **kwargs: admin)
        config = SimpleNamespace()
        testing.pytest_configure(config)
        return config

    return run


def test_the_tests_are_pointed_to_the_database_of_their_own(configure):
    admin = FakeAdmin()

    config = configure("postgresql+psycopg://u:secret@localhost:5432/aireuskadi", admin)

    assert os.environ["DATABASE_URL"].endswith("/aireuskadi_test")
    assert "secret" in os.environ["DATABASE_URL"]  # the password goes on: the tests need it
    assert "aireuskadi_test" in testing.pytest_report_header(config)
    assert admin.disposed


def test_a_server_that_cannot_be_reached_skips_the_database_tests_and_says_why(configure):
    admin = FakeAdmin(
        connect_error=wrapped(OperationalError, pg.OperationalError("Connection refused"))
    )

    config = configure("postgresql+psycopg://u:hunter2xyz@localhost:5432/aireuskadi", admin)

    assert "DATABASE_URL" not in os.environ
    header = testing.pytest_report_header(config)
    assert "cannot connect" in header
    assert "Connection refused" in header
    assert "hunter2xyz" not in header
    assert admin.disposed


def test_a_race_that_never_ends_stops_the_session_instead_of_skipping_silently(configure):
    admin = FakeAdmin(*[BUSY] * testing.ATTEMPTS)

    with pytest.raises(OperationalError):
        configure("postgresql+psycopg://u:p@localhost:5432/aireuskadi", admin)

    assert admin.disposed


def test_a_url_without_a_database_name_is_not_used_for_the_tests(configure):
    # The server would take its default database, which can be the one of the application.
    admin = FakeAdmin()

    config = configure("postgresql+psycopg://u:p@localhost:5432", admin)

    assert "DATABASE_URL" not in os.environ
    assert "no database name" in testing.pytest_report_header(config)
    assert admin.connections == 0


def test_a_url_that_is_already_a_database_of_the_tests_is_left_as_it_is(configure):
    admin = FakeAdmin()
    url = "postgresql+psycopg://u:p@localhost:5432/aireuskadi_test"

    config = configure(url, admin)

    assert os.environ["DATABASE_URL"] == url
    assert testing.pytest_report_header(config) is None
    assert admin.connections == 0


def test_without_database_url_nothing_happens(configure):
    admin = FakeAdmin()

    config = configure(None, admin)

    assert "DATABASE_URL" not in os.environ
    assert testing.pytest_report_header(config) is None
    assert admin.connections == 0
