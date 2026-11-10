"""The WHO 2021 guideline values that `aireuskadi-db-init` loads, against a real PostgreSQL.

The expected figures are written here by hand from Table 3.26 of the WHO global air quality
guidelines (2021), not taken from the code, so that a mistyped value in the seed is caught.
Skipped unless DATABASE_URL points to a database.
"""

import os
from decimal import Decimal

import pytest
from aireuskadi_db import Pollutant, WhoGuideline, create_all, seed_who_guidelines, who
from aireuskadi_db.schema import main
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")

# (pollutant, averaging period) -> ug/m3. The WHO publishes CO in mg/m3 (4 mg/m3); it is stored in
# ug/m3 like everything else, and the 2021 edition has no annual value for O3, SO2 and CO.
PUBLISHED = {
    ("PM25", "annual"): Decimal(5),
    ("PM25", "24h"): Decimal(15),
    ("PM10", "annual"): Decimal(15),
    ("PM10", "24h"): Decimal(45),
    ("NO2", "annual"): Decimal(10),
    ("NO2", "24h"): Decimal(25),
    ("O3", "peak_season"): Decimal(60),
    ("O3", "8h"): Decimal(100),
    ("SO2", "24h"): Decimal(40),
    ("CO", "24h"): Decimal(4000),
}

CLEAR = text("DELETE FROM core.who_guideline WHERE edition = 2021")


@pytest.fixture(autouse=True)
def only_the_database_of_the_tests():
    """These tests delete guidelines: never in the database that holds the real data."""
    assert make_url(URL).database.endswith("_test"), "DATABASE_URL is not the test database"


@pytest.fixture
def engine():
    engine = create_engine(URL)
    create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """A session whose changes are rolled back at the end, and that starts with no guideline of 2021:
    what an earlier run left in the database must not make a test pass. The pollutants are not
    deleted: the loads of the worker point to them."""
    with Session(engine) as session:
        session.execute(CLEAR)
        yield session
        session.rollback()


def loaded(session):
    rows = session.execute(
        select(
            WhoGuideline.pollutant_code, WhoGuideline.averaging_period, WhoGuideline.value_ugm3
        ).where(WhoGuideline.edition == 2021)
    )
    return {(code, period): value for code, period, value in rows}


def test_the_values_of_2021_are_loaded_as_the_who_publishes_them(session):
    seed_who_guidelines(session)

    assert loaded(session) == PUBLISHED


def test_loading_them_again_changes_nothing_and_puts_back_a_value_that_was_changed(session):
    seed_who_guidelines(session)
    session.execute(
        WhoGuideline.__table__.update()
        .where(WhoGuideline.pollutant_code == "NO2", WhoGuideline.averaging_period == "annual")
        .values(value_ugm3=Decimal(40))
    )

    seed_who_guidelines(session)

    assert loaded(session) == PUBLISHED


def test_the_pollutants_that_are_missing_are_created_and_the_existing_ones_are_left_alone(
    session, monkeypatch
):
    # With codes of their own: the real ones may already be in the database, with data pointing to them.
    monkeypatch.setattr(
        who, "POLLUTANTS", [("T_NEW", "New name", "gas"), ("T_OLD", "Name of the seed", "gas")]
    )
    monkeypatch.setattr(who, "GUIDELINES", [("T_NEW", "annual", 1), ("T_OLD", "annual", 2)])
    session.add(Pollutant(code="T_OLD", name="A name set by somebody else"))
    session.flush()

    seed_who_guidelines(session)

    names = {code: name for code, name in session.execute(select(Pollutant.code, Pollutant.name))}
    assert names["T_NEW"] == "New name"
    assert names["T_OLD"] == "A name set by somebody else"


def clear_for_real(engine):
    with Session(engine) as cleaner, cleaner.begin():
        cleaner.execute(CLEAR)


def test_the_command_that_prepares_the_database_loads_them_too(monkeypatch, engine):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.delenv("POSTGRES_READER_USER", raising=False)
    monkeypatch.delenv("POSTGRES_READER_PASSWORD", raising=False)
    # The command commits, and other tests (the ones of the role) run it too and leave the rows:
    # they are cleared for real before it runs, so that only the command can have put them.
    clear_for_real(engine)
    try:
        main()

        with Session(engine) as other:
            assert loaded(other) == PUBLISHED
    finally:
        clear_for_real(engine)
