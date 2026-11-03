"""Fixtures. Tests that use the database are skipped without DATABASE_URL."""

import logging
import os

import pytest
from aireuskadi_db import Pollutant, WhoGuideline, create_all
from emissions_service.main import create_app
from fastapi.testclient import TestClient
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
    # and removed here. Codes that start with TST do not exist in the real data.
    with engine.begin() as conn:
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
    """configure_logging changes the root logger and uvicorn's: put them back after the test."""
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access"]
    saved = [(n, logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in names]
    yield
    for name, handlers, propagate in saved:
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate
