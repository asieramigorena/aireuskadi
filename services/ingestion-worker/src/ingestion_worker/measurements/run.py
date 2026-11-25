"""One run of the measurements loader: the stations and the last hours of the three provinces."""

import hashlib
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from aireuskadi_db import IngestionRun
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ingestion_worker.common.download import download
from ingestion_worker.common.runs import track_run
from ingestion_worker.common.view import refresh_unit_indicator
from ingestion_worker.measurements.load import load_measurements, load_stations, mark_meteo_only
from ingestion_worker.measurements.parse import parse_measurements
from ingestion_worker.measurements.stations import parse_stations

SOURCE = "measurements"
API = "https://api.euskadi.eus/air-quality"
COUNTIES = ("01", "20", "48")  # Araba/Álava, Gipuzkoa, Bizkaia: one request each
HOURLY = API + "/measurements/hourly/counties/{county}/from/{start}/to/{end}"
MINUTE = "%Y-%m-%dT%H:%M"  # with seconds or a Z the API answers 400
DEFAULT_HOURS = 48
MAX_HOURS = 168  # a week


def measurements_hours(now: datetime, last_success: datetime | None) -> int:
    """How many hours back to read: 48, or more to cover the gap if the worker was stopped (the
    values of the stopped hours would be lost otherwise), up to a week."""
    if last_success is None:
        return DEFAULT_HOURS
    gap = math.ceil((now - last_success).total_seconds() / 3600) + 3
    return min(max(DEFAULT_HOURS, gap), MAX_HOURS)


def run_measurements(
    engine: Engine,
    now: datetime | None = None,
    hours: int = DEFAULT_HOURS,
    fetch: Callable[[str], bytes] = download,
) -> None:
    """Loads the stations and the last `hours` hours, which are read again in every run: the
    values of the last hours are corrected and the newest ones are not published yet."""
    now = now or datetime.now(UTC)
    start = (now - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    start, end = start.strftime(MINUTE), now.strftime(MINUTE)

    def work(session: Session, run: IngestionRun) -> None:
        # Everything is downloaded before anything is written: with the retries a download can take
        # minutes, and no row of the database stays locked while it waits.
        stations_file = fetch(f"{API}/stations")
        county_files = [fetch(HOURLY.format(county=c, start=start, end=end)) for c in COUNTIES]

        stations = parse_stations(stations_file.decode())
        values, tried, rejected_parsing, kinds, hours_sent = [], 0, 0, {}, 0
        for file in county_files:
            parsed = parse_measurements(file.decode())
            values += parsed.accepted
            tried += parsed.rows_read
            rejected_parsing += len(parsed.rejected)
            kinds.update(parsed.meteo_only)  # each station is in one county only
            hours_sent += parsed.hours
        # One empty county can happen; all three at once means the API is giving no data.
        if hours_sent == 0:
            raise ValueError("the measurements answer has no hours in any county")

        stations_left_out = load_stations(session, stations.accepted)
        values_left_out = load_measurements(session, values)
        mark_meteo_only(session, kinds)

        run.file_hash = hashlib.sha256(stations_file + b"".join(county_files)).hexdigest()
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
