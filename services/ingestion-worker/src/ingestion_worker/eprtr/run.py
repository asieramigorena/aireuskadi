"""One run of the E-PRTR loader: download, validate, locate, load and record the run."""

import hashlib
import logging
from collections.abc import Callable
from datetime import date

from aireuskadi_db import IngestionRun
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ingestion_worker.boundaries.layers import read_municipalities
from ingestion_worker.common.download import download
from ingestion_worker.common.pollutants import seed_pollutants
from ingestion_worker.common.runs import track_run
from ingestion_worker.common.view import refresh_unit_indicator
from ingestion_worker.eprtr.catalog import catalog_updated_at
from ingestion_worker.eprtr.load import load_emissions
from ingestion_worker.eprtr.locate import locate
from ingestion_worker.eprtr.parse import parse_rows

log = logging.getLogger(__name__)

SOURCE = "eprtr_air"
URL = (
    "https://opendata.euskadi.eus/contenidos/ds_registros/e_prtr_euskadi_{year}/opendata/"
    "aire_eprtr.csv"
)
CATALOG_URL = (
    "https://opendata.euskadi.eus/catalogo/-/"
    "registro-de-emisiones-y-transferencias-de-contaminantes-del-{year}-prtr/"
)


def _source_updated_at(fetch: Callable[[str], bytes], url: str) -> date | None:
    """The date of the last update that the catalog gives. It is not essential to the load, so
    a failure here is logged and the run goes on without the date."""
    try:
        updated = catalog_updated_at(fetch(url).decode("utf-8", errors="replace"))
        reason = "the catalog page has no update date"
    except Exception as error:  # noqa: BLE001 - the date is optional, whatever fails here
        updated, reason = None, str(error)
    if updated is None:
        log.warning("source update date not available", extra={"source": SOURCE, "reason": reason})
    return updated


def run_eprtr(engine: Engine, year: int, fetch: Callable[[str], bytes] = download) -> None:
    url = URL.format(year=year)

    def work(session: Session, run: IngestionRun) -> None:
        data = fetch(url)
        parsed = parse_rows(data.decode("utf-8-sig"))
        seed_pollutants(session)
        located = locate(parsed.accepted, read_municipalities(session))
        rejected_loading = load_emissions(session, located.located)

        run.file_hash = hashlib.sha256(data).hexdigest()
        run.source_updated_at = _source_updated_at(fetch, CATALOG_URL.format(year=year))
        run.rows_read = parsed.rows_read
        run.rows_loaded = len(located.located) - len(rejected_loading)
        run.rows_rejected = len(parsed.rejected) + len(located.rejected) + len(rejected_loading)

    track_run(engine, SOURCE, url, work)

    refresh_unit_indicator(engine)
