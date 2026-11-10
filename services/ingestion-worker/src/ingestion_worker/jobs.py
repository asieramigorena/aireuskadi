"""The loads that the scheduler runs, with how often each has to succeed."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ingestion_worker.boundaries.run import run_boundaries
from ingestion_worker.common.download import download, url_exists
from ingestion_worker.eprtr.run import URL as EPRTR_URL
from ingestion_worker.eprtr.run import run_eprtr
from ingestion_worker.eprtr.years import latest_loaded_year, years_to_load
from ingestion_worker.measurements.run import measurements_hours, run_measurements
from ingestion_worker.scheduler import Job, RunHistory, read_history


def default_jobs(
    engine: Engine | None,
    fetch: Callable[[str], bytes] = download,
    exists: Callable[[int], bool] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    history: Callable[[], dict[str, RunHistory]] | None = None,
    latest_year: Callable[[], int | None] | None = None,
) -> list[Job]:
    """The three loads of the issue: the boundaries and the E-PRTR register every month, the
    measurements every hour. The last two wait for the boundaries, which they are located on.

    The parameters after `fetch` are what a test replaces: the clock, what is published, and what
    the database says about the past."""
    exists = exists or (lambda year: url_exists(EPRTR_URL.format(year=year)))
    history = history or (lambda: read_history(engine))

    def latest() -> int | None:
        if latest_year is not None:
            return latest_year()
        with Session(engine) as session:
            return latest_loaded_year(session)

    def boundaries() -> None:
        run_boundaries(engine, fetch=fetch)

    def eprtr() -> None:
        # Only an edition that exists is asked for: a 404 would be recorded as a failed run.
        for year in years_to_load(latest(), exists, now().year):
            run_eprtr(engine, year, fetch=fetch)

    def measurements() -> None:
        past = history().get("measurements")
        hours = measurements_hours(now(), past.last_success if past else None)
        run_measurements(engine, now=now(), hours=hours, fetch=fetch)

    return [
        Job("boundaries", timedelta(days=30), boundaries),
        Job("eprtr_air", timedelta(days=30), eprtr, requires=("boundaries",)),
        Job("measurements", timedelta(hours=1), measurements, requires=("boundaries",)),
    ]
