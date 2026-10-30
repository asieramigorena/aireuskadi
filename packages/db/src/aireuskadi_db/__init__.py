"""AirEuskadi data model (PostgreSQL + PostGIS, schema ``core``)."""

from aireuskadi_db.base import SCHEMA, Base
from aireuskadi_db.models import (
    ActivitySector,
    District,
    Facility,
    FacilityEmission,
    InventoryEmission,
    Measurement,
    Municipality,
    Pollutant,
    Station,
    Territory,
    WhoGuideline,
)
from aireuskadi_db.schema import create_all
from aireuskadi_db.views import UNIT_INDICATOR_DDL, unit_indicator

__all__ = [
    "SCHEMA",
    "UNIT_INDICATOR_DDL",
    "ActivitySector",
    "Base",
    "District",
    "Facility",
    "FacilityEmission",
    "InventoryEmission",
    "Measurement",
    "Municipality",
    "Pollutant",
    "Station",
    "Territory",
    "WhoGuideline",
    "create_all",
    "unit_indicator",
]
