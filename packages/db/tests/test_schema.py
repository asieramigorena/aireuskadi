"""create_all() against a real PostgreSQL + PostGIS.

Skipped unless DATABASE_URL points to a database, e.g. the one of the local compose.
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from aireuskadi_db import (
    SCHEMA,
    ActivitySector,
    Base,
    District,
    Facility,
    FacilityEmission,
    IngestionRun,
    Measurement,
    Municipality,
    Pollutant,
    Station,
    Territory,
    WhoGuideline,
    create_all,
)
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


@pytest.fixture
def session(engine):
    """A session whose changes are rolled back at the end."""
    with Session(engine) as session:
        yield session
        session.rollback()


def test_a_sector_code_is_unique_within_its_classification_not_across_them(session):
    # SNAP sector 1 and NFR sector 1 are different sectors: the inventory has both.
    session.add_all(
        [
            ActivitySector(classification="T_SNAP", code="1", name="Combustion in energy"),
            ActivitySector(classification="T_NFR", code="1", name="Energy"),
        ]
    )
    session.flush()

    session.add(ActivitySector(classification="T_NFR", code="1", name="The same twice"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_sector_can_have_a_parent_but_the_parent_has_to_exist(session):
    parent = ActivitySector(classification="T_NFR", code="1", name="Energy")
    session.add(parent)
    session.flush()

    child = ActivitySector(
        classification="T_NFR", code="1A", name="Fuel combustion", parent_id=parent.id
    )
    session.add(child)
    session.flush()
    assert (parent.parent_id, child.parent_id) == (None, parent.id)

    session.add(ActivitySector(classification="T_NFR", code="9Z", name="Orphan", parent_id=-1))
    with pytest.raises(IntegrityError):
        session.flush()


NOON = datetime(2026, 11, 1, 12, tzinfo=UTC)


def add_station(session):
    """A station of the test municipality 98001, with a pollutant T_CO."""
    session.add_all(
        [
            Territory(code="98", name="Test"),
            District(code="9801", territory_code="98", name="Test"),
            Municipality(ine_code="98001", district_code="9801", name="Testville", area_km2=10),
            Pollutant(code="T_CO", name="Carbon monoxide"),
        ]
    )
    session.flush()
    station = Station(municipality_code="98001", code="T001", name="Test station")
    session.add(station)
    session.flush()
    return station


def test_a_measurement_has_to_say_its_unit_it_is_not_assumed(session):
    station = add_station(session)

    # CO is published in mg/m3: assuming ug/m3 would store it a thousand times too small.
    session.add(
        Measurement(
            station_id=station.id,
            pollutant_code="T_CO",
            ts=NOON,
            averaging_period="1h",
            value=0.7,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_the_hourly_value_and_the_8_hour_mean_of_the_same_moment_can_both_be_stored(session):
    station = add_station(session)
    key = {"station_id": station.id, "pollutant_code": "T_CO", "ts": NOON, "unit": "mg/m3"}
    session.add_all(
        [
            Measurement(**key, averaging_period="1h", value=0.7),
            Measurement(**key, averaging_period="8h", value=0.5),
        ]
    )
    session.flush()

    session.add(Measurement(**key, averaging_period="8h", value=0.9))
    with pytest.raises(IntegrityError):
        session.flush()


def measure(session, station, pollutant, values, unit, averaging="1h"):
    """One value per hour, from noon on."""
    session.add_all(
        Measurement(
            station_id=station.id,
            pollutant_code=pollutant,
            ts=NOON + timedelta(hours=hour),
            averaging_period=averaging,
            value=value,
            unit=unit,
        )
        for hour, value in enumerate(values)
    )


def guideline(session, pollutant, value_ugm3):
    session.add(
        WhoGuideline(
            pollutant_code=pollutant,
            averaging_period="annual",
            edition=2021,
            value_ugm3=Decimal(value_ugm3),
        )
    )


def who_ratios(session):
    """The WHO ratio of the test municipality for each pollutant, from the refreshed view."""
    session.flush()
    session.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.unit_indicator"))
    rows = session.execute(
        text(
            f"SELECT pollutant_code, who_ratio FROM {SCHEMA}.unit_indicator "
            "WHERE municipality_code = '98001'"
        )
    )
    return {code: None if ratio is None else float(ratio) for code, ratio in rows}


def tonnes(session):
    """(declared_t, t_km2) of the test municipality for each pollutant, from the refreshed view."""
    session.flush()
    session.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.unit_indicator"))
    rows = session.execute(
        text(
            f"SELECT pollutant_code, declared_t, t_km2 FROM {SCHEMA}.unit_indicator "
            "WHERE municipality_code = '98001'"
        )
    )
    return {
        code: tuple(None if x is None else float(x) for x in (declared, density))
        for code, declared, density in rows
    }


def test_a_pollutant_that_was_measured_but_not_declared_has_no_tonnes_and_not_zero(session):
    # Nothing declared means that no facility reported it, not that it was zero: the API shows it
    # as "no data". A zero here would be taken for a declared zero.
    station = add_station(session)
    measure(session, station, "T_CO", [1.0, 3.0], "mg/m3")

    assert tonnes(session) == {"T_CO": (None, None)}


def test_a_declared_pollutant_has_its_tonnes_and_its_tonnes_per_km2(session):
    station = add_station(session)
    measure(session, station, "T_CO", [1.0, 3.0], "mg/m3")
    facility = Facility(municipality_code="98001", nima="T9800001", name="Test facility")
    session.add(facility)
    session.flush()
    session.add(
        FacilityEmission(
            facility_id=facility.id, pollutant_code="T_CO", year=NOON.year, amount_kg=5000
        )
    )

    # 5000 kg are 5 t, over the 10 km2 of the municipality.
    assert tonnes(session) == {"T_CO": (5.0, 0.5)}


def test_the_who_ratio_compares_values_in_the_same_unit(session):
    station = add_station(session)
    session.add(Pollutant(code="T_NO2", name="Nitrogen dioxide"))
    session.flush()
    measure(session, station, "T_CO", [1.0, 3.0], "mg/m3")  # mean 2 mg/m3 = 2000 ug/m3
    measure(session, station, "T_NO2", [20.0, 20.0], "µg/m3")
    guideline(session, "T_CO", "4000")  # the WHO figure for CO is in mg/m3; 4 mg/m3 = 4000 ug/m3
    guideline(session, "T_NO2", "40")

    assert who_ratios(session) == {"T_CO": 0.5, "T_NO2": 0.5}


def test_the_8_hour_mean_does_not_count_in_the_annual_mean_of_the_hourly_values(session):
    station = add_station(session)
    measure(session, station, "T_CO", [2.0, 2.0], "mg/m3")
    measure(session, station, "T_CO", [100.0, 100.0], "mg/m3", averaging="8h")
    guideline(session, "T_CO", "4000")

    assert who_ratios(session) == {"T_CO": 0.5}


def test_a_value_in_an_unknown_unit_is_left_out_instead_of_guessed(session):
    station = add_station(session)
    measure(session, station, "T_CO", [5.0], "furlongs")
    guideline(session, "T_CO", "4000")

    assert who_ratios(session) == {}


def test_a_station_is_identified_by_the_code_it_has_in_the_network_and_two_cannot_share_it(session):
    add_station(session)  # code T001

    session.add(Station(municipality_code="98001", code="T001", name="The same code again"))
    with pytest.raises(IntegrityError):
        session.flush()
