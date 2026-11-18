"""GET /inventory: the yearly emissions of the whole Basque Country by sector, from the inventory
of the Basque Government (1990 to the last edition). There is no municipality in it."""

from typing import Annotated, Literal

from aireuskadi_db import ActivitySector, InventoryEmission
from aireuskadi_http import INVALID_REQUEST, NOT_FOUND
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from emissions_service.database import SessionDep
from emissions_service.validation import PollutantParam

router = APIRouter()

ATTRIBUTION = (
    "Eusko Jaurlaritza / Gobierno Vasco: Inventario de emisiones a la atmósfera de la "
    "C.A. de Euskadi (Open Data Euskadi, CC BY 4.0)"
)
# SNAP and NFR are two ways of splitting the same total into sectors; TOTAL is a pollutant that
# is only published as a total (methane).
Classification = Literal["SNAP", "NFR", "TOTAL"]


class SectorOut(BaseModel):
    code: str
    name: str


class InventoryPointOut(BaseModel):
    sector: SectorOut
    year: int
    value: float


class InventoryOut(BaseModel):
    attribution: str
    pollutant: str
    unit: str
    classification: str
    series: list[InventoryPointOut]


@router.get("/inventory", responses={**INVALID_REQUEST, **NOT_FOUND})
def inventory(
    session: SessionDep,
    pollutant: PollutantParam,
    classification: Classification = "SNAP",
    sector: Annotated[str | None, Query(max_length=5, pattern=r"^[A-Z0-9]+$")] = None,
    # `from` is a word of Python: the parameters keep the names of the URL with an alias.
    start: Annotated[int | None, Query(alias="from", ge=1990, le=2100)] = None,
    end: Annotated[int | None, Query(alias="to", ge=1990, le=2100)] = None,
) -> InventoryOut:
    query = (
        select(
            ActivitySector.code,
            ActivitySector.name,
            InventoryEmission.year,
            InventoryEmission.value,
            InventoryEmission.unit,
        )
        .join(ActivitySector)
        .where(
            InventoryEmission.pollutant_code == pollutant,
            ActivitySector.classification == classification,
        )
        .order_by(ActivitySector.code, InventoryEmission.year)
    )
    if sector is not None:
        query = query.where(ActivitySector.code == sector)
    if start is not None:
        query = query.where(InventoryEmission.year >= start)
    if end is not None:
        query = query.where(InventoryEmission.year <= end)
    rows = session.execute(query).all()
    if not rows:
        raise StarletteHTTPException(404, "No inventory data for this selection.")
    return InventoryOut(
        attribution=ATTRIBUTION,
        pollutant=pollutant,
        unit=rows[0].unit,
        classification=classification,
        series=[
            InventoryPointOut(
                sector=SectorOut(code=r.code, name=r.name), year=r.year, value=r.value
            )
            for r in rows
        ],
    )
