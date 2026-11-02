"""The jobs of the scheduler. Skipped without DATABASE_URL (see conftest.py).

The downloads are fakes; the database is the real one and `engine` (conftest.py) cleans up.
"""

import re
from datetime import UTC, datetime, timedelta

from aireuskadi_db import IngestionRun
from fakes import FILE, fake_fetch
from ingestion_worker.jobs import default_jobs
from ingestion_worker.scheduler import RunHistory
from sqlalchemy import select
from sqlalchemy.orm import Session

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def job(jobs, source):
    return next(j for j in jobs if j.source == source)


def test_the_jobs_are_the_ones_of_the_issue_with_their_intervals_and_what_they_wait_for():
    jobs = default_jobs(engine=None)

    assert [(j.source, j.every, j.requires) for j in jobs] == [
        ("boundaries", timedelta(days=30), ()),
        ("eprtr_air", timedelta(days=30), ("boundaries",)),
        ("measurements", timedelta(hours=1), ("boundaries",)),
    ]


def test_the_measurements_job_reads_back_far_enough_to_cover_a_gap_after_a_stop(engine, boundaries):
    requested = []
    history = {"measurements": RunHistory(NOW - timedelta(hours=100), NOW - timedelta(hours=100))}
    jobs = default_jobs(
        engine, fetch=fake_fetch(requested), now=lambda: NOW, history=lambda: history
    )

    job(jobs, "measurements").run()

    start = re.search(r"/counties/01/from/(.+?)/to/", requested[1]).group(1)
    assert start == "2026-10-29T08:00"  # 103 hours before 15:00 on 2 November, from the hour


def test_the_eprtr_job_loads_the_year_it_has_and_the_next_one_if_the_register_published_it(
    engine, boundaries
):
    requested = []

    def fetch(url):
        requested.append(url)
        return FILE if "e_prtr_euskadi" in url else b""

    jobs = default_jobs(
        engine,
        fetch=fetch,
        exists=lambda year: year in (2023, 2024),
        latest_year=lambda: 2023,
        now=lambda: NOW,
    )

    job(jobs, "eprtr_air").run()

    files = [u for u in requested if u.endswith("aire_eprtr.csv")]
    assert [re.search(r"e_prtr_euskadi_(\d+)", u).group(1) for u in files] == ["2023", "2024"]
    with Session(engine) as session:
        runs = session.scalars(select(IngestionRun).where(IngestionRun.source == "eprtr_air")).all()
        assert [r.status for r in runs[-2:]] == ["succeeded", "succeeded"]
