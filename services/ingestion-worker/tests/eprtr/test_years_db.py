"""latest_loaded_year against a real PostgreSQL. Skipped without DATABASE_URL (conftest.py)."""

from conftest import layers
from ingestion_worker.boundaries.layers import load_boundaries
from ingestion_worker.common.pollutants import seed_pollutants
from ingestion_worker.eprtr.load import load_emissions
from ingestion_worker.eprtr.locate import LocatedEmission
from ingestion_worker.eprtr.parse import Emission
from ingestion_worker.eprtr.years import latest_loaded_year


def test_the_latest_loaded_year_is_the_highest_year_of_the_emissions(session):
    load_boundaries(session, *layers())
    seed_pollutants(session)
    emission = Emission(
        "T000000001", "030402", 1.0, 500_000.0, 4_705_000.0, 2, "A FACTORY", "x", 2099
    )
    load_emissions(session, [LocatedEmission(emission, "99001", -3.0, 42.5)])

    assert latest_loaded_year(session) == 2099  # no real edition has this year
