"""Fixtures. Tests that use the database are skipped without DATABASE_URL."""

import logging
import os
import sys
from datetime import UTC, datetime

import pytest
from aireuskadi_db import (
    District,
    Facility,
    FacilityEmission,
    Measurement,
    Municipality,
    Pollutant,
    Station,
    Territory,
    WhoGuideline,
    create_all,
)
from emissions_service.main import create_app
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def square(x, y, size):
    """MULTIPOLYGON of a square whose lower left corner is (x, y)."""
    x1, y1 = round(x + size, 6), round(y + size, 6)
    return WKTElement(
        f"MULTIPOLYGON((({x} {y}, {x1} {y}, {x1} {y1}, {x} {y1}, {x} {y})))", srid=4326
    )


def add_test_units(session):
    """The units of the tests: territory 99 > district 9901 > municipalities 99001 (10 km2) and
    99002 (30 km2), and district 9902 > municipality 99003 (60 km2). The full boundary of each is a square and the simplified one a smaller
    square, so that a test can tell which of the two the API served."""
    if session.get(Territory, "99") is not None:
        return
    session.add(
        Territory(
            code="99",
            name="Test territory",
            geom=square(-2.1, 42.9, 0.4),
            geom_simplified=square(-2.09, 42.91, 0.38),
        )
    )
    session.add(
        District(
            code="9901",
            territory_code="99",
            name="Test district",
            geom=square(-2.05, 42.95, 0.3),
            geom_simplified=square(-2.04, 42.96, 0.28),
        )
    )
    session.add(
        District(
            code="9902",
            territory_code="99",
            name="Other test district",
            geom=square(-1.7, 42.95, 0.2),
            geom_simplified=square(-1.69, 42.96, 0.18),
        )
    )
    session.flush()
    units = (
        ("99001", "9901", "Testville", 10, -2.0),
        ("99002", "9901", "Testburg", 30, -1.9),
        ("99003", "9902", "Testdorf", 60, -1.7),
    )
    for code, district, name, area, x in units:
        session.add(
            Municipality(
                ine_code=code,
                district_code=district,
                name=name,
                area_km2=area,
                geom=square(x, 43.0, 0.1),
                geom_simplified=square(round(x + 0.01, 6), 43.01, 0.08),
            )
        )
    session.flush()


@pytest.fixture
def engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    engine = create_engine(url)
    create_all(engine)
    yield engine
    # The API reads through its own connection, so what a test writes has to be committed
    # and removed here. Codes that start with TST (pollutants), T0000000 (NIMA) and 99 (units)
    # do not exist in the real data.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM core.measurement WHERE pollutant_code LIKE 'TST%'"))
        conn.execute(text("DELETE FROM core.station WHERE code LIKE 'T0000000%'"))
        conn.execute(text("DELETE FROM core.facility_emission WHERE pollutant_code LIKE 'TST%'"))
        conn.execute(text("DELETE FROM core.facility WHERE nima LIKE 'T0000000%'"))
        conn.execute(text("DELETE FROM core.municipality WHERE ine_code LIKE '99%'"))
        conn.execute(text("DELETE FROM core.district WHERE code LIKE '99%'"))
        conn.execute(text("DELETE FROM core.territory WHERE code = '99'"))
        conn.execute(text("DELETE FROM core.who_guideline WHERE pollutant_code LIKE 'TST%'"))
        conn.execute(text("DELETE FROM core.pollutant WHERE code LIKE 'TST%'"))
        # The view keeps the rows of the test data until it is refreshed.
        conn.execute(text("REFRESH MATERIALIZED VIEW core.unit_indicator"))


@pytest.fixture
def client(engine):
    return TestClient(create_app(engine))


@pytest.fixture
def add_pollutant(engine):
    def add(code, name, group=None, guidelines=()):
        with Session(engine) as session:
            session.add(Pollutant(code=code, name=name, group=group))
            session.flush()
            for period, edition, value in guidelines:
                session.add(
                    WhoGuideline(
                        pollutant_code=code,
                        averaging_period=period,
                        edition=edition,
                        value_ugm3=value,
                    )
                )
            session.commit()

    return add


@pytest.fixture(autouse=True)
def keep_logging_state():
    """app_from_env sets up the logging (the root logger, uvicorn's, sys.excepthook): put it back
    after the test."""
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access"]
    saved = [(n, logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in names]
    level, hook = logging.getLogger().level, sys.excepthook
    yield
    for name, handlers, propagate in saved:
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate
    logging.getLogger().setLevel(level)
    sys.excepthook = hook


@pytest.fixture
def add_facility(engine):
    """A facility at (lon, lat), or without a position if lon is None, with its emissions
    [(pollutant, year, kg), ...], in a test municipality (99001 unless another is given) that is
    created the first time."""

    def add(
        nima, lon, lat, emissions=(), name="Test facility", activity=None, municipality="99001"
    ):
        with Session(engine) as session:
            add_test_units(session)
            facility = Facility(
                municipality_code=municipality,
                nima=nima,
                name=name,
                activity=activity,
                geom=None if lon is None else WKTElement(f"POINT({lon} {lat})", srid=4326),
            )
            session.add(facility)
            session.flush()
            for pollutant, year, kg in emissions:
                session.add(
                    FacilityEmission(
                        facility_id=facility.id, pollutant_code=pollutant, year=year, amount_kg=kg
                    )
                )
            session.commit()
            return facility.id

    return add


@pytest.fixture
def refresh_indicators(engine):
    """The indicators of the units are a materialized view: the worker refreshes it after each
    load, a test does it after writing its rows."""

    def refresh():
        with engine.begin() as conn:
            conn.execute(text("REFRESH MATERIALIZED VIEW core.unit_indicator"))

    return refresh


@pytest.fixture
def add_measurements(engine):
    """Hourly values (all in the same unit) of a pollutant in the year 2023, measured by a
    station of test municipality 99001."""

    def add(pollutant, values, unit="µg/m3", station="T0000000S"):
        with Session(engine) as session:
            add_test_units(session)
            found = session.query(Station).filter_by(code=station).one_or_none()
            if found is None:
                found = Station(municipality_code="99001", code=station, name="Test station")
                session.add(found)
                session.flush()
            for hour, value in enumerate(values):
                session.add(
                    Measurement(
                        station_id=found.id,
                        pollutant_code=pollutant,
                        ts=datetime(2023, 3, 1, hour, tzinfo=UTC),
                        averaging_period="1h",
                        value=value,
                        unit=unit,
                    )
                )
            session.commit()

    return add
