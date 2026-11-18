"""run_inventory against a real PostgreSQL. Skipped without DATABASE_URL.

A run commits; the fixture `engine` deletes the inventory and the runs that the tests write.
"""

import pytest
from aireuskadi_db import IngestionRun, InventoryEmission
from fakes import inventory_fetch as serving
from fakes import inventory_files
from ingestion_worker.inventory.parse import LayoutChanged
from ingestion_worker.inventory.run import file_url, newest_edition, run_inventory
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def last_run(engine):
    with Session(engine) as session:
        return session.scalars(
            select(IngestionRun)
            .where(IngestionRun.source == "inventory")
            .order_by(IngestionRun.id.desc())
        ).first()


def rows(engine):
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(InventoryEmission))


def test_a_run_loads_the_edition_and_is_recorded(engine):
    run_inventory(engine, 1991, fetch=serving(inventory_files()))

    run = last_run(engine)
    assert (run.status, run.rows_loaded, run.rows_rejected) == ("succeeded", rows(engine), 0)
    assert run.rows_loaded > 0
    assert run.file_hash


def test_the_same_files_again_are_a_succeeded_run_that_loads_nothing(engine):
    fetch = serving(inventory_files())
    run_inventory(engine, 1991, fetch=fetch)
    loaded = rows(engine)

    run_inventory(engine, 1991, fetch=fetch)

    run = last_run(engine)
    assert (run.status, run.rows_read, run.rows_loaded) == ("succeeded", 0, 0)
    assert rows(engine) == loaded


def test_asked_by_hand_the_same_files_are_loaded_again(engine):
    # So that a fix of the parser or the loader reaches an edition that is already loaded.
    fetch = serving(inventory_files())
    run_inventory(engine, 1991, fetch=fetch)

    run_inventory(engine, 1991, fetch=fetch, skip_unchanged=False)

    run = last_run(engine)
    assert run.status == "succeeded"
    assert run.rows_loaded == rows(engine) > 0


def test_a_changed_layout_is_a_failed_run_and_the_old_rows_stay(engine):
    run_inventory(engine, 1991, fetch=serving(inventory_files()))
    loaded = rows(engine)

    with pytest.raises(LayoutChanged):
        run_inventory(engine, 1991, fetch=serving(inventory_files(missing=("2.8",))))

    assert last_run(engine).status == "failed"
    assert rows(engine) == loaded


def test_the_newest_edition_is_this_year_or_the_closest_one_published():
    assert newest_edition(lambda year: year == 2024, 2026) == 2024
    assert newest_edition(lambda year: False, 2026) is None
    assert file_url("2_ECA_SNAP", 2024) == (
        "https://opendata.euskadi.eus/contenidos/estadistica/amb_ca_eca_2024/opendata/es_tablas/"
        "2_ECA_SNAP_90a24_es.xlsx"
    )
