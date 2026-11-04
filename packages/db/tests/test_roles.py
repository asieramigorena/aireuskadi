"""The read-only role of the services that only read: what it can and cannot do.

Skipped unless DATABASE_URL points to a database whose user can create roles (the owner).
The tests connect as the role itself and try things; the role is dropped afterwards.
"""

import os

import pytest
from aireuskadi_db import SCHEMA, Base, create_all, create_reader_role
from aireuskadi_db.schema import main
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")

USER = "t_reader_test"
PASSWORD = "first-Pa55_word"


@pytest.fixture
def owner():
    engine = create_engine(URL)
    create_all(engine)
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


@pytest.mark.parametrize(
    "statement",
    [
        f"INSERT INTO {SCHEMA}.pollutant (code, name) VALUES ('TSTX', 'x')",
        f"UPDATE {SCHEMA}.pollutant SET name = 'x'",
        f"DELETE FROM {SCHEMA}.pollutant",
        f"DROP TABLE {SCHEMA}.pollutant",
        f"CREATE TABLE {SCHEMA}.leftover (id integer)",
    ],
)
def test_trying_to_change_something_fails_even_after_switching_the_read_only_mode_off(
    reader, statement
):
    with pytest.raises(DBAPIError), reader.connect() as conn:
        conn.execute(text("SET default_transaction_read_only = off"))
        conn.execute(text(statement))


def test_a_write_is_also_refused_by_the_read_only_mode_of_the_role(reader):
    with pytest.raises(DBAPIError, match="read-only"), reader.connect() as conn:
        conn.execute(text(f"INSERT INTO {SCHEMA}.pollutant (code, name) VALUES ('TSTX', 'x')"))


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


def test_a_password_with_quotes_and_symbols_is_taken_as_it_is(owner):
    tricky = 'it\'s "a" pa$$word; DROP ROLE x;--'

    create_reader_role(owner, USER, tricky)

    with reader_engine(tricky).connect() as conn:
        conn.execute(text("SELECT 1"))


@pytest.mark.parametrize("user", ["", "reader; DROP TABLE x", "a" * 64, "Reader Role"])
def test_a_name_that_is_not_a_plain_role_name_is_refused(owner, user):
    with pytest.raises(ValueError, match="role name"):
        create_reader_role(owner, user, PASSWORD)


def test_an_empty_password_is_refused(owner):
    with pytest.raises(ValueError, match="password"):
        create_reader_role(owner, USER, "")


def test_running_it_again_puts_back_what_somebody_changed_by_hand(owner, reader):
    with owner.begin() as conn:
        conn.execute(text(f"GRANT INSERT, UPDATE ON {SCHEMA}.pollutant TO {USER}"))
        conn.execute(text(f"GRANT SELECT ON {SCHEMA}.ingestion_run TO {USER}"))
        conn.execute(text(f"GRANT CREATE ON SCHEMA {SCHEMA} TO {USER}"))
        conn.execute(
            text(
                f"ALTER ROLE {USER} SUPERUSER CREATEDB CREATEROLE REPLICATION BYPASSRLS "
                "CONNECTION LIMIT 99"
            )
        )
        conn.execute(text(f"ALTER ROLE {USER} RESET default_transaction_read_only"))
        conn.execute(text(f"ALTER ROLE {USER} RESET statement_timeout"))

    create_reader_role(owner, USER, PASSWORD)

    with owner.connect() as conn:
        role = conn.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, "
                "rolconnlimit FROM pg_roles WHERE rolname = :r"
            ),
            {"r": USER},
        ).one()
        assert tuple(role) == (False, False, False, False, False, 10)
        for table, privilege in [
            ("pollutant", "INSERT"),
            ("pollutant", "UPDATE"),
            ("ingestion_run", "SELECT"),
        ]:
            assert not conn.scalar(
                text("SELECT has_table_privilege(:r, :t, :p)"),
                {"r": USER, "t": f"{SCHEMA}.{table}", "p": privilege},
            )
        assert not conn.scalar(
            text("SELECT has_schema_privilege(:r, :s, 'CREATE')"), {"r": USER, "s": SCHEMA}
        )
    with reader_engine(PASSWORD).connect() as conn:
        assert conn.scalar(text("SHOW statement_timeout")) == "5s"
        assert conn.scalar(text("SHOW default_transaction_read_only")) == "on"


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


def test_the_command_does_not_create_a_role_without_credentials(owner, monkeypatch):
    monkeypatch.delenv("POSTGRES_READER_USER", raising=False)
    monkeypatch.delenv("POSTGRES_READER_PASSWORD", raising=False)

    main()

    with owner.connect() as conn:
        assert not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": USER})


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
