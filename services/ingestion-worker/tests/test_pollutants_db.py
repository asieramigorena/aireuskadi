"""seed_pollutants against a real PostgreSQL. Skipped without DATABASE_URL (see conftest.py)."""

from aireuskadi_db import Pollutant
from ingestion_worker.pollutants import seed_pollutants
from sqlalchemy import func, select


def code_of(session, eprtr_code):
    return session.scalar(select(Pollutant.code).where(Pollutant.eprtr_code == eprtr_code))


def test_each_eprtr_code_leads_to_its_pollutant(session):
    seed_pollutants(session)

    assert code_of(session, "030402") == "NOX"  # oxides of nitrogen
    assert code_of(session, "060101") == "PM10"
    assert code_of(session, "020302") == "LEAD"


def test_seeding_twice_does_not_duplicate_the_pollutants(session):
    seed_pollutants(session)
    first = session.scalar(select(func.count()).select_from(Pollutant))

    seed_pollutants(session)

    assert session.scalar(select(func.count()).select_from(Pollutant)) == first
