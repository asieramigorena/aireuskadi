"""load_boundaries against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL.

Every test works inside a transaction that is rolled back, so no row stays in the database.
"""

import pytest
from aireuskadi_db import District, Municipality, Territory
from conftest import layers
from fakes import wiggly_pair
from ingestion_worker.boundaries.layers import load_boundaries, municipality_records
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


def test_the_simplified_geometry_is_stored_next_to_the_full_one(session):
    territories, districts, _ = layers()
    load_boundaries(session, territories, districts, municipality_records(wiggly_pair()))

    srid, kind, simplified, full = session.execute(
        select(
            func.ST_SRID(Municipality.geom_simplified),
            func.ST_GeometryType(Municipality.geom_simplified),
            func.ST_NPoints(Municipality.geom_simplified),
            func.ST_NPoints(Municipality.geom),
        ).where(Municipality.ine_code == "99001")
    ).one()
    assert (srid, kind) == (4326, "ST_MultiPolygon")
    assert simplified < full / 5


def test_territories_and_districts_have_a_simplified_geometry_too(session):
    load_boundaries(session, *layers())

    for model in (Territory, District):
        assert session.scalar(
            select(func.count()).select_from(model).where(model.geom_simplified.is_not(None))
        ), model.__name__


def test_loading_again_replaces_the_simplified_geometry(session):
    territories, districts, _ = layers()
    load_boundaries(session, territories, districts, municipality_records(wiggly_pair()))
    load_boundaries(session, *layers())  # the same municipality, now a plain square

    points = session.scalar(
        select(func.ST_NPoints(Municipality.geom_simplified)).where(
            Municipality.ine_code == "99001"
        )
    )
    assert points == 5
