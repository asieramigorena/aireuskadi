"""AirEuskadi data model (PostgreSQL + PostGIS): the data in schema ``core``, the accounts in ``auth``."""

from aireuskadi_db.base import AUTH_SCHEMA, SCHEMA, Base
from aireuskadi_db.models import (
    ActivitySector,
    AppUser,
    District,
    Facility,
    FacilityEmission,
    IngestionRun,
    InventoryEmission,
    Measurement,
    Municipality,
    Pollutant,
    Station,
    Territory,
    WhoGuideline,
)
from aireuskadi_db.roles import create_reader_role
from aireuskadi_db.schema import migrate
from aireuskadi_db.views import UNIT_INDICATOR_DDL, unit_indicator
from aireuskadi_db.who import seed_who_guidelines

__all__ = [
    "AUTH_SCHEMA",
    "SCHEMA",
    "UNIT_INDICATOR_DDL",
    "ActivitySector",
    "AppUser",
    "Base",
    "District",
    "Facility",
    "FacilityEmission",
    "IngestionRun",
    "InventoryEmission",
    "Measurement",
    "Municipality",
    "Pollutant",
    "Station",
    "Territory",
    "WhoGuideline",
    "create_reader_role",
    "migrate",
    "seed_who_guidelines",
    "unit_indicator",
]
