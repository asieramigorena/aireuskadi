"""load_stations and load_measurements against a real PostgreSQL. Skipped without DATABASE_URL.

The tests use the municipality 99001, which does not exist in the real boundaries.
"""

from datetime import UTC, datetime, timedelta

import pytest
from aireuskadi_db import Measurement, Station
from conftest import layers
from ingestion_worker.boundaries.layers import load_boundaries
from ingestion_worker.common.pollutants import seed_pollutants
from ingestion_worker.measurements.load import load_measurements, load_stations
from ingestion_worker.measurements.parse import MeasurementRecord
from ingestion_worker.measurements.stations import StationRecord
from sqlalchemy import func, select


@pytest.fixture
def reference(session):
    """What a load needs to exist: a municipality and the pollutants."""
    load_boundaries(session, *layers())
    seed_pollutants(session)


def station(code="T-1", name="TEST STATION", municipality="99001", lon=-3.0, lat=42.5):
    return StationRecord(code, name, municipality, lon, lat)


def test_a_station_is_stored_with_its_municipality_and_position_and_an_unknown_municipality_is_rejected(
    session, reference, caplog
):
    known = station(code="T-1", lon=-3.0, lat=42.5)
    unknown = station(code="T-2", municipality="99999")

    with caplog.at_level("WARNING", logger="ingestion_worker.measurements.load"):
        rejected = load_stations(session, [known, unknown])

    stored = session.scalar(select(Station).where(Station.code == "T-1"))
    assert (stored.name, stored.municipality_code) == ("TEST STATION", "99001")
    assert session.scalar(select(func.ST_X(Station.geom)).where(Station.id == stored.id)) == -3.0
    assert session.scalar(select(func.ST_Y(Station.geom)).where(Station.id == stored.id)) == 42.5
    assert session.scalar(select(func.ST_SRID(Station.geom)).where(Station.id == stored.id)) == 4326
    assert (
        session.scalar(select(func.count()).select_from(Station).where(Station.code == "T-2")) == 0
    )
    (row,) = rejected
    assert (row.code, "99999" in row.reason) == ("T-2", True)
    (record,) = caplog.records
    assert (record.getMessage(), record.source, record.station) == (
        "station rejected",
        "stations",
        "T-2",
    )


def test_loading_a_station_again_keeps_one_row_with_the_latest_data(session, reference):
    load_stations(session, [station(name="OLD NAME")])

    load_stations(session, [station(name="NEW NAME")])

    rows = session.scalars(select(Station).where(Station.code == "T-1")).all()
    session.refresh(rows[0])
    assert [r.name for r in rows] == ["NEW NAME"]


NOON = datetime(2026, 11, 1, 12, tzinfo=UTC)


def reading(station="T-1", pollutant="NO2", value=18.0, hour=0, averaging="1h", unit="µg/m3"):
    return MeasurementRecord(
        station, pollutant, averaging, NOON + timedelta(hours=hour), value, unit
    )


@pytest.fixture
def with_station(session, reference):
    load_stations(session, [station(code="T-1")])


def stored(session, **filters):
    return session.scalars(select(Measurement).filter_by(**filters)).all()


def test_a_measurement_is_stored_with_its_station_pollutant_hour_averaging_value_and_unit(
    session, with_station
):
    load_measurements(session, [reading(pollutant="CO", value=0.4, unit="mg/m3", averaging="8h")])

    (row,) = stored(
        session, station_id=good_station_id(session), pollutant_code="CO", averaging_period="8h"
    )
    assert (float(row.value), row.unit, row.ts) == (0.4, "mg/m3", NOON)
    assert row.station.code == "T-1"


def test_a_measurement_of_an_unknown_station_or_pollutant_is_rejected_and_logged_and_the_rest_stay(
    session, with_station, caplog
):
    good = reading(value=18.0)
    no_station = reading(station="T-404")
    no_pollutant = reading(pollutant="UNOBTAINIUM")

    with caplog.at_level("WARNING", logger="ingestion_worker.measurements.load"):
        rejected = load_measurements(session, [good, no_station, no_pollutant])

    assert [float(m.value) for m in stored(session, station_id=good_station_id(session))] == [18.0]
    assert [
        (r.station_code, "station" in r.reason or "pollutant" in r.reason) for r in rejected
    ] == [
        ("T-404", True),
        ("T-1", True),
    ]
    assert {r.getMessage() for r in caplog.records} == {"row rejected"}
    assert {r.source for r in caplog.records} == {"measurements"}


def good_station_id(session):
    return session.scalar(select(Station.id).where(Station.code == "T-1"))


def test_reading_the_same_hours_again_updates_the_values_and_does_not_duplicate(
    session, with_station
):
    load_measurements(session, [reading(value=18.0, hour=0), reading(value=20.0, hour=1)])

    load_measurements(session, [reading(value=19.0, hour=0), reading(value=21.0, hour=1)])

    rows = stored(session, station_id=good_station_id(session))
    for row in rows:
        session.refresh(row)
    assert sorted(float(r.value) for r in rows) == [19.0, 21.0]


def test_a_load_of_twelve_thousand_values_is_split_so_it_does_not_hit_the_parameter_limit(
    session, with_station
):
    # PostgreSQL takes 65535 parameters per statement and each value uses six.
    records = [reading(value=float(hour), hour=hour) for hour in range(12_000)]

    rejected = load_measurements(session, records)

    assert rejected == []
    count = session.scalar(
        select(func.count())
        .select_from(Measurement)
        .where(Measurement.station_id == good_station_id(session))
    )
    assert count == 12_000


def test_the_same_value_twice_in_one_load_keeps_the_last_instead_of_failing(session, with_station):
    load_measurements(session, [reading(value=18.0), reading(value=25.0)])  # same hour twice

    (row,) = stored(session, station_id=good_station_id(session))
    assert float(row.value) == 25.0
