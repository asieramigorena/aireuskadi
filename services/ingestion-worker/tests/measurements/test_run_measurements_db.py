"""run_measurements against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL.

A run commits, because the view can only be refreshed after the commit; the fixture `engine`
(conftest.py) removes the stations T-* and their measurements afterwards.
"""

import hashlib
from datetime import UTC, datetime

import pytest
from aireuskadi_db import IngestionRun, Measurement, Station
from fakes import API, COUNTY_48, STATIONS, fake_fetch
from ingestion_worker.measurements.run import run_measurements
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

NOW = datetime(2026, 11, 2, 14, 13, tzinfo=UTC)


def test_a_run_loads_the_stations_and_the_values_of_the_last_48_hours_and_records_the_counts(
    engine, boundaries
):
    requested = []

    run_measurements(engine, now=NOW, fetch=fake_fetch(requested))

    assert requested == [
        f"{API}/stations",
        f"{API}/measurements/hourly/counties/01/from/2026-10-31T14:00/to/2026-11-02T14:13",
        f"{API}/measurements/hourly/counties/20/from/2026-10-31T14:00/to/2026-11-02T14:13",
        f"{API}/measurements/hourly/counties/48/from/2026-10-31T14:00/to/2026-11-02T14:13",
    ]
    with Session(engine) as session:
        run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        assert (run.source, run.status, run.error) == ("measurements", "succeeded", None)
        # 1 station + 3 values tried (NO2, CO, Mercurio): 4 read, 3 loaded, 1 rejected.
        assert (run.rows_read, run.rows_loaded, run.rows_rejected) == (4, 3, 1)
        body = f"{STATIONS}[][]{COUNTY_48}".encode()
        assert run.file_hash == hashlib.sha256(body).hexdigest()
        assert (
            session.scalar(select(func.count()).select_from(Station).where(Station.code == "T-1"))
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(Measurement)
                .join(Station)
                .where(Station.code == "T-1")
            )
            == 2
        )
        in_the_view = session.scalar(
            text(
                "SELECT count(*) FROM core.unit_indicator "
                "WHERE municipality_code = '99001' AND pollutant_code = 'NO2'"
            )
        )
        assert in_the_view == 1  # the view was refreshed after the load


def count(engine, sql):
    with engine.connect() as conn:
        return conn.scalar(text(sql))


def test_if_one_province_fails_the_run_is_failed_and_nothing_stays_not_even_the_stations(
    engine, boundaries
):
    ok = fake_fetch()
    measurements_before = count(engine, "SELECT count(*) FROM core.measurement")

    def fetch(url):
        if "/counties/20/" in url:
            raise RuntimeError("Gipuzkoa is down")
        return ok(url)

    with pytest.raises(RuntimeError, match="Gipuzkoa is down"):
        run_measurements(engine, now=NOW, fetch=fetch)

    with Session(engine) as session:
        run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        assert (run.source, run.status) == ("measurements", "failed")
        assert "Gipuzkoa is down" in run.error
    assert count(engine, "SELECT count(*) FROM core.station WHERE code = 'T-1'") == 0
    assert count(engine, "SELECT count(*) FROM core.measurement") == measurements_before


def test_running_it_again_every_hour_does_not_duplicate_anything(engine, boundaries):
    run_measurements(engine, now=NOW, fetch=fake_fetch())
    run_measurements(engine, now=NOW, fetch=fake_fetch())

    assert count(engine, "SELECT count(*) FROM core.station WHERE code = 'T-1'") == 1
    assert (
        count(
            engine,
            "SELECT count(*) FROM core.measurement m JOIN core.station s ON s.id = m.station_id "
            "WHERE s.code = 'T-1'",
        )
        == 2
    )
