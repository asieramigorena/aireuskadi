"""Pollutants of the E-PRTR register and the code each one has in core.pollutant."""

import csv
from importlib import resources

from aireuskadi_db import Pollutant
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def seed_pollutants(session: Session) -> None:
    """Writes the pollutants of data/pollutants.csv. Existing ones are updated, not duplicated."""
    text = (
        resources.files("ingestion_worker.common")
        .joinpath("data/pollutants.csv")
        .read_text("utf-8")
    )
    rows = list(csv.DictReader(text.splitlines()))
    for row in rows:
        # A pollutant that is only measured has no E-PRTR code: NULL, not an empty string, which
        # would be the same value for all of them and break the unique key.
        row["eprtr_code"] = row["eprtr_code"] or None
    statement = insert(Pollutant).values(rows)
    update = {c: statement.excluded[c] for c in ("name", "group", "eprtr_code")}
    session.execute(statement.on_conflict_do_update(index_elements=["code"], set_=update))
