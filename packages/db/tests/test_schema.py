"""The schema (made by migrate()) against a real PostgreSQL + PostGIS.

Skipped unless DATABASE_URL points to a database, e.g. the one of the local compose.
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from aireuskadi_db import (
    SCHEMA,
    District,
    Facility,
    FacilityEmission,
    Measurement,
    Municipality,
    Pollutant,
    Station,
    Territory,
    WhoGuideline,
    migrate,
    seed_who_guidelines,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")


@pytest.fixture
def engine():
    engine = create_engine(URL)
    migrate(engine)
    return engine


@pytest.fixture
def session(engine):
    """A session whose changes are rolled back at the end."""
    with Session(engine) as session:
        yield session
        session.rollback()


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


def test_the_seeded_who_values_are_the_ones_the_view_divides_by(session):
    # The view reads the guideline whose period is "annual": the seed has to use that exact word.
    seed_who_guidelines(session)
    station = add_station(session)
    measure(session, station, "NO2", [20.0, 20.0], "µg/m3")  # the WHO annual value is 10
    measure(session, station, "O3", [50.0, 50.0], "µg/m3")  # no annual value in 2021

    assert who_ratios(session) == {"NO2": 2.0, "O3": None}


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
