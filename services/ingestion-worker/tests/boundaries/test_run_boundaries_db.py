"""run_boundaries against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL (conftest)."""

from aireuskadi_db import IngestionRun, Municipality
from fakes import fetch
from ingestion_worker.boundaries.run import run_boundaries
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_a_run_downloads_the_three_layers_loads_the_municipalities_and_records_the_counts(engine):
    run_boundaries(engine, fetch=fetch)

    with Session(engine) as session:
        run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        assert (run.source, run.status, run.error) == ("boundaries", "succeeded", None)
        assert (run.rows_read, run.rows_loaded, run.rows_rejected) == (2, 1, 1)
        assert run.file_hash is not None and len(run.file_hash) == 64
        assert [
            m.name
            for m in session.scalars(select(Municipality).where(Municipality.ine_code.like("99%")))
        ] == ["Testville"]
