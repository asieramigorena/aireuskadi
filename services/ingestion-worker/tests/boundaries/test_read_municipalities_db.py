"""read_municipalities against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL."""

import pytest
from conftest import layers
from ingestion_worker.boundaries.layers import load_boundaries, read_municipalities


def test_municipalities_come_back_in_metres_so_that_points_in_metres_can_be_located(session):
    load_boundaries(session, *layers())

    municipalities = read_municipalities(session)

    assert municipalities.crs == "EPSG:25830"
    town = municipalities[municipalities["ine_code"] == "99001"].geometry.iloc[0]
    # The test square is 10 km x 10 km: 100 km2 = 100 million m2, after a round trip to degrees.
    assert town.area == pytest.approx(100_000_000, rel=0.001)
