"""The accounts of the site (auth.app_user).

Skipped unless DATABASE_URL is set. Each test starts with no accounts.
"""

import os

import pytest
from aireuskadi_db import migrate
from aireuskadi_db.accounts import Accounts
from aireuskadi_db.admin_cli import main
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")


@pytest.fixture
def engine():
    engine = create_engine(URL)
    migrate(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM auth.app_user"))
    yield engine
    engine.dispose()


@pytest.fixture
def accounts(engine):
    return Accounts(sessionmaker(engine, expire_on_commit=False))


def test_a_name_with_capitals_is_refused_by_the_table_itself(engine):
    # Grafana does not tell "User1" from "user1": two such accounts would be one Grafana user.
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO auth.app_user (username) VALUES ('User1')"))


def test_an_added_account_logs_in_with_its_password_and_only_with_it(accounts):
    accounts.add("user1", "a-long-password-1")

    assert accounts.authenticate(" User1 ", "a-long-password-1").username == "user1"
    assert accounts.authenticate("user1", "wrong-password-1") is None
    assert accounts.authenticate("nobody", "a-long-password-1") is None


def test_a_password_longer_than_bcrypt_reads_is_a_wrong_password_not_an_error(accounts):
    accounts.add("user1", "a-long-password-1")

    assert accounts.authenticate("user1", "x" * 100) is None


def test_the_password_is_stored_as_a_bcrypt_hash_and_the_account_is_not_an_admin(accounts):
    user = accounts.add("user1", "a-long-password-1")

    assert user.hashed_password.startswith("$2")
    assert "a-long-password-1" not in user.hashed_password
    assert user.is_admin is False


@pytest.mark.parametrize(
    ("name", "password"),
    [
        ("ab", "a-long-password-1"),
        ("user 1", "a-long-password-1"),
        ("user1", "abcd"),
        ("user1", "x" * 73),  # bcrypt reads only 72 bytes
    ],
)
def test_a_bad_name_or_a_short_password_is_refused(accounts, name, password):
    with pytest.raises(ValueError):
        accounts.add(name, password)


def test_a_name_that_is_taken_is_refused(accounts):
    accounts.add("user1", "a-long-password-1")

    with pytest.raises(ValueError):
        accounts.add("USER1", "another-password-2")


def test_the_command_adds_promotes_and_lists_and_never_prints_the_password(
    engine, accounts, monkeypatch, capsys
):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "a-long-password-1")

    main(["add", "user1"])
    main(["promote", "user1"])
    main(["list"])

    output = capsys.readouterr()
    assert "user1" in output.out
    assert "a-long-password-1" not in output.out + output.err
    assert "$2" not in output.out + output.err
    assert accounts.find_by_name("user1").is_admin is True


def test_the_command_stops_if_the_two_passwords_differ(engine, accounts, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    typed = iter(["a-long-password-1", "a-long-password-2"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(typed))

    with pytest.raises(SystemExit, match="do not match"):
        main(["add", "user1"])
    assert accounts.find_by_name("user1") is None


@pytest.mark.parametrize(
    ("name", "password"),
    [("user1", "a" * 12), ("ab", "a" * 12), ("user2", "abcd"), ("Us er", "a" * 12)],
)
def test_a_sign_up_with_a_taken_or_bad_name_or_a_short_password_is_none(accounts, name, password):
    accounts.add("user1", "a" * 12)

    assert accounts.sign_up(name, password) is None


@pytest.mark.parametrize("password", ["a" * 73, "wrong-password-1"])
@pytest.mark.parametrize("name", ["user1", "nobody"])
def test_every_failed_login_costs_one_bcrypt_check_whatever_the_account(
    accounts, monkeypatch, name, password
):
    # How long a login takes must not say whether the account exists: a password longer than
    # bcrypt reads, or a name that does not exist, costs the same slow check as a wrong password.
    accounts.add("user1", "a" * 12)
    checks = []
    monkeypatch.setattr(
        "aireuskadi_db.accounts.verify_password", lambda *args: checks.append(1) or False
    )

    assert accounts.authenticate(name, password) is None
    assert checks == [1]


def test_a_password_of_five_characters_is_enough(accounts):
    assert accounts.sign_up("user3", "abcde") is not None
    assert accounts.authenticate("user3", "abcde") is not None
