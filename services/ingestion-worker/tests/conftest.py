"""Database fixtures. Tests that use `session` are skipped without DATABASE_URL."""

import os

import geopandas as gpd
import pytest
from aireuskadi_db import IngestionRun, create_all
from ingestion_worker.boundaries import (
    district_records,
    load_boundaries,
    municipality_records,
    territory_records,
)
from shapely.geometry import box
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


@pytest.fixture
def session():
    """A session on the real database; whatever the test writes is rolled back at the end."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    engine = create_engine(url)
    create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()


# Codes that do not exist in the real data, so a test can never clash with loaded boundaries.
SQUARE = box(495_000, 4_700_000, 505_000, 4_710_000)


def layers(name="Testville"):
    def layer(**columns):
        return gpd.GeoDataFrame(columns, geometry=[SQUARE], crs="EPSG:25830")

    return (
        territory_records(layer(TERRITORIO=["TEST"], PRO_PROV=["99"])),
        district_records(layer(COMARCA=["TEST DISTRICT"], COM_PROV=["99"], COM_COM=["01"])),
        municipality_records(
            layer(
                NOMBRE_TOP=[name],
                EUSTAT=["99001"],
                MUN_PROV=["99"],
                MUN_COMR=["01"],
                MUN_MUNI=["1"],
            )
        ),
    )


@pytest.fixture
def engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    engine = create_engine(url)
    create_all(engine)
    with Session(engine) as session:
        first_run = session.scalar(select(IngestionRun.id).order_by(IngestionRun.id.desc()))
    yield engine
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM core.facility_emission WHERE facility_id IN "
                "(SELECT id FROM core.facility WHERE nima LIKE 'T0000000%')"
            )
        )
        conn.execute(text("DELETE FROM core.facility WHERE nima LIKE 'T0000000%'"))
        conn.execute(text("DELETE FROM core.municipality WHERE ine_code = '99001'"))
        conn.execute(text("DELETE FROM core.district WHERE code = '9901'"))
        conn.execute(text("DELETE FROM core.territory WHERE code = '99'"))
        conn.execute(text("DELETE FROM core.ingestion_run WHERE id > :id"), {"id": first_run or 0})
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY core.unit_indicator"))


@pytest.fixture
def boundaries(engine):
    with Session(engine) as session:
        load_boundaries(session, *layers())
        session.commit()
