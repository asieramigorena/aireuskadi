"""Writes the located E-PRTR emissions to core.facility and core.facility_emission."""

import logging

from aireuskadi_db import Facility, FacilityEmission, Pollutant
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ingestion_worker.eprtr import RejectedRow
from ingestion_worker.locate import LocatedEmission

log = logging.getLogger(__name__)


def load_emissions(session: Session, located: list[LocatedEmission]) -> list[RejectedRow]:
    """Inserts new rows and updates existing ones; returns the rows it left out.

    A row whose pollutant code is not in core.pollutant is left out and logged. It does not
    commit: the caller owns the transaction.
    """
    pollutants = dict(session.execute(select(Pollutant.eprtr_code, Pollutant.code)).all())
    rejected = []
    known = []
    for item in located:
        emission = item.emission
        if emission.pollutant_code in pollutants:
            known.append(item)
            continue
        reason = f"pollutant code {emission.pollutant_code} is not in core.pollutant"
        rejected.append(RejectedRow(emission.row_number, emission.nima, reason))
        log.warning(
            "row rejected",
            extra={
                "source": "eprtr_air",
                "row_number": emission.row_number,
                "nima": emission.nima,
                "reason": reason,
            },
        )
    if not known:
        return rejected
    located = known
    facility_rows = {
        item.emission.nima: {
            "nima": item.emission.nima,
            "name": item.emission.facility_name,
            "activity": item.emission.activity,
            "municipality_code": item.ine_code,
            "geom": from_shape(Point(item.longitude, item.latitude), srid=4326),
        }
        for item in located
    }
    statement = insert(Facility).values(list(facility_rows.values()))
    update = {c: statement.excluded[c] for c in ("name", "activity", "municipality_code", "geom")}
    ids = session.execute(
        statement.on_conflict_do_update(index_elements=["nima"], set_=update).returning(
            Facility.nima, Facility.id
        )
    ).all()
    facility_id = dict(ids)

    emission_rows = [
        {
            "facility_id": facility_id[item.emission.nima],
            "pollutant_code": pollutants[item.emission.pollutant_code],
            "year": item.emission.year,
            "amount_kg": item.emission.amount_kg,
        }
        for item in located
    ]
    statement = insert(FacilityEmission).values(emission_rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["facility_id", "pollutant_code", "year"],
            set_={"amount_kg": statement.excluded.amount_kg},
        )
    )
    session.flush()
    return rejected
