"""load_boundaries against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL.

Every test works inside a transaction that is rolled back, so no row stays in the database.
"""

import pytest
from aireuskadi_db import Municipality
from conftest import layers
from ingestion_worker.boundaries import load_boundaries
from sqlalchemy import func, select


def test_a_loaded_municipality_is_read_back_with_its_district_area_and_geometry_in_degrees(session):
    load_boundaries(session, *layers())

    town = session.get(Municipality, "99001")
    assert (town.name, town.district_code) == ("Testville", "9901")
    assert float(town.area_km2) == pytest.approx(100.0, abs=0.001)
    assert (
        session.scalar(
            select(func.ST_SRID(Municipality.geom)).where(Municipality.ine_code == "99001")
        )
        == 4326
    )


def test_loading_twice_keeps_one_row_and_updates_it(session):
    load_boundaries(session, *layers(name="Testville"))
    load_boundaries(session, *layers(name="Renamed"))

    towns = session.scalars(select(Municipality).where(Municipality.ine_code == "99001")).all()
    assert [t.name for t in towns] == ["Renamed"]
