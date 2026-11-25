"""load_inventory against a real PostgreSQL. Skipped without DATABASE_URL; `session` rolls back."""

from aireuskadi_db import ActivitySector, InventoryEmission
from ingestion_worker.common.pollutants import seed_pollutants
from ingestion_worker.inventory.load import load_inventory
from ingestion_worker.inventory.parse import InventoryRow
from sqlalchemy import select


def stored(session):
    query = select(
        InventoryEmission.pollutant_code,
        ActivitySector.classification,
        ActivitySector.code,
        InventoryEmission.year,
        InventoryEmission.value,
        InventoryEmission.unit,
    ).join(ActivitySector)
    return sorted(tuple(row) for row in session.execute(query))


def test_the_rows_are_stored_with_their_sector_and_unit_t(session):
    seed_pollutants(session)

    load_inventory(
        session,
        [
            InventoryRow("SOX", "SNAP", "01", "Combustión", 1990, 10.5),
            InventoryRow("SOX", "SNAP", "01", "Combustión", 1991, 9.0),
        ],
    )

    assert stored(session) == [
        ("SOX", "SNAP", "01", 1990, 10.5, "t"),
        ("SOX", "SNAP", "01", 1991, 9.0, "t"),
    ]
    sector = session.scalars(select(ActivitySector).where(ActivitySector.code == "01")).one()
    assert (sector.classification, sector.name, sector.parent_id) == ("SNAP", "Combustión", None)


def test_a_second_load_replaces_the_first_one(session):
    seed_pollutants(session)
    load_inventory(session, [InventoryRow("SOX", "SNAP", "01", "Combustión", 1990, 1.0)])

    load_inventory(session, [InventoryRow("NOX", "SNAP", "02", "Plantas", 1990, 2.0)])

    assert stored(session) == [("NOX", "SNAP", "02", 1990, 2.0, "t")]
