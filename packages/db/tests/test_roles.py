"""The read-only role of the services that only read: what it can and cannot do.

Skipped unless DATABASE_URL points to a database whose user can create roles (the owner).
The tests connect as the role itself and try things; the role is dropped afterwards.
"""

import os

import pytest
from aireuskadi_db import SCHEMA, Base, create_reader_role, migrate
from aireuskadi_db.schema import main
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")

USER = "t_reader_test"
PASSWORD = "first-Pa55_word"


@pytest.fixture
def owner():
    engine = create_engine(URL)
    migrate(engine)
    yield engine
    with engine.begin() as conn:
        if conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": USER}):
            conn.execute(text(f"DROP OWNED BY {USER}"))  # takes its privileges away first
            conn.execute(text(f"DROP ROLE {USER}"))
    engine.dispose()


@pytest.fixture
def reader(owner):
    create_reader_role(owner, USER, PASSWORD)
    engine = reader_engine(PASSWORD)
    # The role has to be able to log in: otherwise a test that expects an error would pass
    # because the connection itself fails.
    with engine.connect():
        pass
    yield engine
    engine.dispose()


def reader_engine(password):
    return create_engine(make_url(URL).set(username=USER, password=password))


def test_it_can_read_what_the_services_read(reader):
    tables = [
        "pollutant", "who_guideline", "facility", "facility_emission", "municipality",
        "district", "territory", "station", "measurement", "inventory_emission",
        "activity_sector", "unit_indicator",
    ]  # fmt: skip
    with reader.connect() as conn:
        for table in tables:
            conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.{table}"))


def test_it_cannot_read_the_record_of_the_loads(reader):
    # ingestion_run holds source URLs, file hashes and error texts: nothing that is served.
    with pytest.raises(ProgrammingError, match="permission denied"), reader.connect() as conn:
        conn.execute(text(f"SELECT * FROM {SCHEMA}.ingestion_run"))


def test_it_has_no_privilege_to_change_anything(owner, reader):
    changes = ["INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
    with owner.connect() as conn:
        for table in Base.metadata.tables.values():
            for privilege in changes:
                assert not conn.scalar(
                    text("SELECT has_table_privilege(:r, :t, :p)"),
                    {"r": USER, "t": str(table.fullname), "p": privilege},
                ), f"{privilege} on {table.fullname}"
        assert not conn.scalar(
            text("SELECT has_schema_privilege(:r, :s, 'CREATE')"), {"r": USER, "s": SCHEMA}
        )


def test_it_cannot_do_what_only_an_administrator_does(owner, reader):
    with owner.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, "
                "rolcanlogin, rolconnlimit FROM pg_roles WHERE rolname = :r"
            ),
            {"r": USER},
        ).one()
    assert tuple(row) == (False, False, False, False, False, True, 10)


def test_a_query_that_takes_more_than_five_seconds_is_cut_by_the_role_itself(reader):
    with reader.connect() as conn:
        assert conn.scalar(text("SHOW statement_timeout")) == "5s"


def test_running_it_again_changes_the_password_and_keeps_everything_else(owner, reader):
    create_reader_role(owner, USER, "second-Pa55_word")

    # The old password is not tried: a refused login is a FATAL of PostgreSQL that no setting of a
    # database or a role silences, and it would show up as an error of the application. A role has
    # one password, so if the new one logs in the old one is gone.
    with reader_engine("second-Pa55_word").connect() as conn:
        conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.pollutant"))
        assert conn.scalar(text("SHOW statement_timeout")) == "5s"


# The command line: aireuskadi-db-init creates the role when the environment has its credentials.


def test_the_command_creates_the_role_when_the_environment_has_its_credentials(
    owner, monkeypatch, capsys
):
    monkeypatch.setenv("POSTGRES_READER_USER", USER)
    monkeypatch.setenv("POSTGRES_READER_PASSWORD", PASSWORD)

    main()

    with reader_engine(PASSWORD).connect() as conn:
        conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.pollutant"))
    output = capsys.readouterr().out
    assert USER in output
    assert PASSWORD not in output  # the password is never printed


@pytest.mark.parametrize(
    ("user", "password"), [(USER, None), (None, PASSWORD), (USER, ""), ("", PASSWORD)]
)
def test_the_command_refuses_half_of_the_credentials_instead_of_guessing(
    owner, monkeypatch, user, password
):
    for name, value in [("POSTGRES_READER_USER", user), ("POSTGRES_READER_PASSWORD", password)]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit, match="POSTGRES_READER_USER"):
        main()
