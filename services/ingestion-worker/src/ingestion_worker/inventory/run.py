"""One run of the inventory loader: download the three files, skip them if they are the same as
last time, otherwise validate, load and record the run."""

import hashlib
import logging
from collections.abc import Callable

from aireuskadi_db import IngestionRun
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from ingestion_worker.common.download import download, url_exists
from ingestion_worker.common.pollutants import seed_pollutants
from ingestion_worker.common.runs import track_run
from ingestion_worker.inventory.load import load_inventory
from ingestion_worker.inventory.parse import parse_inventory

log = logging.getLogger(__name__)

SOURCE = "inventory"
# The year of the edition is in the folder and, with two digits, in the name: 2024 -> ..._90a24_.
URL = (
    "https://opendata.euskadi.eus/contenidos/estadistica/amb_ca_eca_{year}/opendata/es_tablas/"
    "{name}_90a{short}_es.xlsx"
)
FILES = ("1_ECA_CAPV", "2_ECA_SNAP", "3_ECA_NFR")  # 4_UE_ECA is not used: it is about countries
LOOKBACK = 4  # how many years back to look for the newest edition


def file_url(name: str, year: int) -> str:
    return URL.format(year=year, name=name, short=f"{year % 100:02d}")


def edition_exists(year: int) -> bool:
    """Whether the edition has been published (a HEAD request to its first file)."""
    return url_exists(file_url("1_ECA_CAPV", year))


def newest_edition(exists: Callable[[int], bool], this_year: int) -> int | None:
    """The newest edition that has been published, or None if there is none in the last years."""
    for year in range(this_year, this_year - LOOKBACK - 1, -1):
        if exists(year):
            return year
    return None


def _last_hash(session: Session) -> str | None:
    """The file hash of the last run that succeeded."""
    return session.scalar(
        select(IngestionRun.file_hash)
        .where(IngestionRun.source == SOURCE, IngestionRun.status == "succeeded")
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    )


def run_inventory(
    engine: Engine,
    year: int,
    fetch: Callable[[str], bytes] = download,
    skip_unchanged: bool = True,
) -> None:
    """Loads the edition `year`. If its files are the same as last time it loads nothing, unless
    `skip_unchanged` is False (a load by hand: e.g. after a fix of the parser)."""

    def work(session: Session, run: IngestionRun) -> None:
        files = [fetch(file_url(name, year)) for name in FILES]
        file_hash = hashlib.sha256(b"".join(files)).hexdigest()
        # The same files as last time: nothing to do, but the run is recorded as a success so
        # that the scheduler waits a month before looking again.
        if skip_unchanged and file_hash == _last_hash(session):
            log.info("inventory unchanged", extra={"source": SOURCE, "edition": year})
            run.rows_read = run.rows_loaded = run.rows_rejected = 0
        else:
            rows = parse_inventory(*files, edition=year)
            seed_pollutants(session)
            load_inventory(session, rows)
            run.rows_read = run.rows_loaded = len(rows)
            run.rows_rejected = 0
        run.file_hash = file_hash

    track_run(engine, SOURCE, file_url("*", year), work)
