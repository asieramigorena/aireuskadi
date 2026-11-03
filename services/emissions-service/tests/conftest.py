"""Fixtures. Tests that use the database are skipped without DATABASE_URL."""

import logging
import os
import sys

import pytest
from aireuskadi_db import (
    District,
    Facility,
    FacilityEmission,
    Municipality,
    Pollutant,
    Territory,
    WhoGuideline,
    create_all,
)
from emissions_service.main import create_app
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


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
        conn.execute(text("DELETE FROM core.facility_emission WHERE pollutant_code LIKE 'TST%'"))
        conn.execute(text("DELETE FROM core.facility WHERE nima LIKE 'T0000000%'"))
        conn.execute(text("DELETE FROM core.municipality WHERE ine_code = '99001'"))
        conn.execute(text("DELETE FROM core.district WHERE code = '9901'"))
        conn.execute(text("DELETE FROM core.territory WHERE code = '99'"))
        conn.execute(text("DELETE FROM core.who_guideline WHERE pollutant_code LIKE 'TST%'"))
        conn.execute(text("DELETE FROM core.pollutant WHERE code LIKE 'TST%'"))


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
    [(pollutant, year, kg), ...], in a test municipality (99001) that is created the first time."""

    def add(nima, lon, lat, emissions=(), name="Test facility", activity=None):
        with Session(engine) as session:
            if session.get(Municipality, "99001") is None:
                session.add(Territory(code="99", name="Test territory"))
                session.add(District(code="9901", territory_code="99", name="Test district"))
                session.add(
                    Municipality(
                        ine_code="99001", district_code="9901", name="Testville", area_km2=10
                    )
                )
                session.flush()
            facility = Facility(
                municipality_code="99001",
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
