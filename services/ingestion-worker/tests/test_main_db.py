"""The command line of the worker. Skipped without DATABASE_URL (see conftest.py)."""

from aireuskadi_db import IngestionRun
from ingestion_worker.main import main
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_run_boundaries_db import fetch as boundaries_fetch
from test_run_eprtr_db import FILE


def last_run(engine):
    with Session(engine) as session:
        return session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()


def test_the_eprtr_command_loads_the_year_it_is_given(engine, boundaries):
    urls = []

    def fetch(url):
        urls.append(url)
        return FILE

    main(["eprtr", "--year", "2023"], engine=engine, fetch=fetch)

    assert "e_prtr_euskadi_2023" in urls[0]
    assert last_run(engine).source == "eprtr_air"


def test_the_boundaries_command_loads_the_boundaries(engine):
    main(["boundaries"], engine=engine, fetch=boundaries_fetch)

    assert last_run(engine).source == "boundaries"
