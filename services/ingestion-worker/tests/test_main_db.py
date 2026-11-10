"""The command line of the worker. Skipped without DATABASE_URL (see conftest.py)."""

import re
from datetime import datetime, timedelta

from aireuskadi_db import IngestionRun
from fakes import FILE, fake_fetch
from fakes import fetch as boundaries_fetch
from ingestion_worker.main import main
from sqlalchemy import select
from sqlalchemy.orm import Session


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


def test_the_measurements_command_loads_the_stations_and_the_values(engine, boundaries):
    main(["measurements"], engine=engine, fetch=fake_fetch())

    assert last_run(engine).source == "measurements"


def test_the_hours_option_sets_how_far_back_the_values_are_read(engine, boundaries):
    requested = []

    main(["measurements", "--hours", "6"], engine=engine, fetch=fake_fetch(requested))

    start, end = (
        datetime.strptime(part, "%Y-%m-%dT%H:%M")
        for part in re.search(r"/from/(.+)/to/(.+)", requested[1]).groups()
    )
    assert timedelta(hours=6) <= end - start < timedelta(hours=7)  # from the hour, 6 h back
