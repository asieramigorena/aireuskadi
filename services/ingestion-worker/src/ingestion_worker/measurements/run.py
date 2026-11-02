"""One run of the measurements loader: the stations and the last hours of the three provinces."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from aireuskadi_db import IngestionRun
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ingestion_worker.common.download import download
from ingestion_worker.common.runs import track_run
from ingestion_worker.common.view import refresh_unit_indicator
from ingestion_worker.measurements.load import load_measurements, load_stations
from ingestion_worker.measurements.parse import parse_measurements
from ingestion_worker.measurements.stations import parse_stations

SOURCE = "measurements"
API = "https://api.euskadi.eus/air-quality"
COUNTIES = ("01", "20", "48")  # Araba/Álava, Gipuzkoa, Bizkaia: one request each
HOURLY = API + "/measurements/hourly/counties/{county}/from/{start}/to/{end}"
MINUTE = "%Y-%m-%dT%H:%M"  # with seconds or a Z the API answers 400


def run_measurements(
    engine: Engine,
    now: datetime | None = None,
    hours: int = 48,
    fetch: Callable[[str], bytes] = download,
) -> None:
    """Loads the stations and the last `hours` hours, which are read again in every run: the
    values of the last hours are corrected and the newest ones are not published yet."""
    now = now or datetime.now(UTC)
    start = (now - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    start, end = start.strftime(MINUTE), now.strftime(MINUTE)

    def work(session: Session, run: IngestionRun) -> None:
        stations_file = fetch(f"{API}/stations")
        stations = parse_stations(stations_file.decode())
        stations_left_out = load_stations(session, stations.accepted)

        files = [stations_file]
        values, tried, rejected_parsing = [], 0, 0
        for county in COUNTIES:
            file = fetch(HOURLY.format(county=county, start=start, end=end))
            files.append(file)
            parsed = parse_measurements(file.decode())
            values += parsed.accepted
            tried += parsed.rows_read
            rejected_parsing += len(parsed.rejected)
        values_left_out = load_measurements(session, values)

        run.file_hash = hashlib.sha256(b"".join(files)).hexdigest()
        run.rows_read = len(stations.accepted) + len(stations.rejected) + tried
        run.rows_loaded = (len(stations.accepted) - len(stations_left_out)) + (
            len(values) - len(values_left_out)
        )
        run.rows_rejected = (
            len(stations.rejected)
            + len(stations_left_out)
            + rejected_parsing
            + len(values_left_out)
        )

    track_run(engine, SOURCE, HOURLY.format(county="*", start="*", end="*"), work)
    refresh_unit_indicator(engine)
