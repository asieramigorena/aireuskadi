"""Writes the stations and the measurements of the air quality network to core."""

import logging

from aireuskadi_db import Measurement, Municipality, Pollutant, Station
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ingestion_worker.measurements.parse import MeasurementRecord, RejectedValue
from ingestion_worker.measurements.stations import RejectedStation, StationRecord

log = logging.getLogger(__name__)

# Rows per INSERT: PostgreSQL takes at most 65535 parameters in a statement and each row uses 6.
CHUNK = 5000


def load_stations(session: Session, stations: list[StationRecord]) -> list[RejectedStation]:
    """Writes the stations; one whose municipality is not in core.municipality is left out and
    logged. It does not commit: the caller owns the transaction."""
    known = set(session.scalars(select(Municipality.ine_code)))
    rejected = []
    rows = []
    for item in stations:
        if item.municipality_code not in known:
            reason = f"municipality {item.municipality_code} is not in core.municipality"
            rejected.append(RejectedStation(item.code, reason))
            log.warning(
                "station rejected",
                extra={"source": "stations", "station": item.code, "reason": reason},
            )
            continue
        rows.append(
            {
                "code": item.code,
                "name": item.name,
                "municipality_code": item.municipality_code,
                "geom": from_shape(Point(item.longitude, item.latitude), srid=4326),
            }
        )
    if rows:
        statement = insert(Station).values(rows)
        update = {c: statement.excluded[c] for c in ("name", "municipality_code", "geom")}
        session.execute(statement.on_conflict_do_update(index_elements=["code"], set_=update))
    return rejected


def load_measurements(session: Session, records: list[MeasurementRecord]) -> list[RejectedValue]:
    """Writes the values, replacing those that are already there for the same station,
    pollutant, hour and averaging period. A value of a station or a pollutant that is not in
    core is left out and logged. It does not commit: the caller owns the transaction."""
    stations = dict(session.execute(select(Station.code, Station.id)).all())
    pollutants = set(session.scalars(select(Pollutant.code)))
    rejected = []
    rows = {}  # by key, so that a value that comes twice is written once: the last one
    for record in records:
        if record.station_code not in stations:
            reason = f"station {record.station_code} is not in core.station"
        elif record.pollutant_code not in pollutants:
            reason = f"pollutant {record.pollutant_code} is not in core.pollutant"
        else:
            key = (
                stations[record.station_code],
                record.pollutant_code,
                record.ts,
                record.averaging_period,
            )
            rows[key] = {
                "station_id": key[0],
                "pollutant_code": key[1],
                "ts": key[2],
                "averaging_period": key[3],
                "value": record.value,
                "unit": record.unit,
            }
            continue
        rejected.append(
            RejectedValue(record.station_code, record.ts, record.pollutant_code, reason)
        )
        log.warning(
            "row rejected",
            extra={
                "source": "measurements",
                "station": record.station_code,
                "ts": record.ts.isoformat(),
                "pollutant_name": record.pollutant_code,
                "reason": reason,
            },
        )
    rows = list(rows.values())
    for start in range(0, len(rows), CHUNK):
        statement = insert(Measurement).values(rows[start : start + CHUNK])
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["station_id", "pollutant_code", "ts", "averaging_period"],
                set_={"value": statement.excluded.value, "unit": statement.excluded.unit},
            )
        )
    return rejected
