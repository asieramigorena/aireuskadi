"""Writes the inventory to core.activity_sector and core.inventory_emission."""

from aireuskadi_db import ActivitySector, InventoryEmission
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ingestion_worker.inventory.parse import InventoryRow


def load_inventory(session: Session, rows: list[InventoryRow]) -> None:
    """Replaces the inventory with `rows`: each edition publishes every year again, corrected.

    The sectors are added or renamed, never deleted (nothing else points to them). It does not
    commit: the caller owns the transaction.
    """
    sectors = {(row.classification, row.sector_code): row.sector_name for row in rows}
    statement = insert(ActivitySector).values(
        [
            {"classification": classification, "code": code, "name": name}
            for (classification, code), name in sectors.items()
        ]
    )
    ids = session.execute(
        statement.on_conflict_do_update(
            constraint="activity_sector_code", set_={"name": statement.excluded.name}
        ).returning(ActivitySector.classification, ActivitySector.code, ActivitySector.id)
    ).all()
    sector_id = {(classification, code): id for classification, code, id in ids}

    session.execute(delete(InventoryEmission))
    session.execute(
        insert(InventoryEmission).values(
            [
                {
                    "pollutant_code": row.pollutant_code,
                    "activity_sector_id": sector_id[(row.classification, row.sector_code)],
                    "year": row.year,
                    "value": row.value,
                    "unit": "t",
                }
                for row in rows
            ]
        )
    )
    session.flush()
