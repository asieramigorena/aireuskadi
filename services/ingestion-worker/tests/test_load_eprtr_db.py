"""load_emissions against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL.

The tests use the municipality 99001, which does not exist in the real boundaries.
"""

import pytest
from aireuskadi_db import Facility
from conftest import layers
from ingestion_worker.boundaries import load_boundaries
from ingestion_worker.eprtr import Emission
from ingestion_worker.load_eprtr import load_emissions
from ingestion_worker.locate import LocatedEmission
from ingestion_worker.pollutants import seed_pollutants
from sqlalchemy import func, select


@pytest.fixture
def reference(session):
    """The reference data an E-PRTR load needs: a municipality and the pollutants."""
    load_boundaries(session, *layers())
    seed_pollutants(session)


def located(nima="0100000001", pollutant="030402", amount=100.0, name="A FACTORY", row_number=2):
    emission = Emission(
        nima, pollutant, amount, 500_000.0, 4_705_000.0, row_number, name, "0146 - Pigs", 2023
    )
    return LocatedEmission(emission, "99001", -3.0, 42.5)


def test_a_located_emission_creates_its_facility_and_its_emission_row(session, reference):
    load_emissions(session, [located()])

    facility = session.scalar(select(Facility).where(Facility.nima == "0100000001"))
    assert (facility.name, facility.activity, facility.municipality_code) == (
        "A FACTORY",
        "0146 - Pigs",
        "99001",
    )
    assert (
        session.scalar(select(func.ST_SRID(Facility.geom)).where(Facility.id == facility.id))
        == 4326
    )
    assert (
        session.scalar(select(func.ST_X(Facility.geom)).where(Facility.id == facility.id)) == -3.0
    )
    (emission,) = facility.emissions
    assert (emission.pollutant_code, emission.year, float(emission.amount_kg)) == (
        "NOX",
        2023,
        100.0,
    )


def test_loading_again_keeps_one_facility_and_one_row_with_the_latest_data(session, reference):
    load_emissions(session, [located(name="OLD NAME", amount=100.0)])

    load_emissions(session, [located(name="NEW NAME", amount=250.5)])

    facility = session.scalar(select(Facility).where(Facility.nima == "0100000001"))
    session.refresh(facility)
    assert facility.name == "NEW NAME"
    (emission,) = facility.emissions
    assert float(emission.amount_kg) == 250.5


def test_an_unknown_pollutant_code_is_rejected_and_logged_and_the_others_are_loaded(
    session, reference, caplog
):
    known = located(nima="0100000001", pollutant="030402", row_number=2)
    unknown = located(nima="0100000001", pollutant="999999", row_number=3)

    with caplog.at_level("WARNING", logger="ingestion_worker.load_eprtr"):
        rejected = load_emissions(session, [known, unknown])

    (row,) = rejected
    assert (row.row_number, row.nima) == (3, "0100000001")
    assert "999999" in row.reason
    (record,) = caplog.records
    assert record.getMessage() == "row rejected"
    assert (record.source, record.row_number, record.nima) == ("eprtr_air", 3, "0100000001")
    facility = session.scalar(select(Facility).where(Facility.nima == "0100000001"))
    assert [e.pollutant_code for e in facility.emissions] == ["NOX"]


def test_loading_nothing_is_fine_when_every_row_was_rejected_before(session, reference):
    assert load_emissions(session, []) == []
