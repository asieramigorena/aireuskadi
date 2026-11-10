"""The facilities of the E-PRTR register: the points of the map and the card of each one."""

from typing import Annotated

from aireuskadi_db import Facility, FacilityEmission, Municipality, Pollutant
from aireuskadi_http import INVALID_REQUEST, NOT_FOUND
from fastapi import APIRouter, Path
from pydantic import BaseModel
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from emissions_service.database import SessionDep
from emissions_service.validation import PollutantParam, YearParam, refuse_year_out_of_range

router = APIRouter()

INTEGER_MAX = 2**31 - 1  # the biggest value of a PostgreSQL integer column, like facility.id


class LocationOut(BaseModel):
    lon: float
    lat: float


class MunicipalityOut(BaseModel):
    code: str
    name: str


class FacilityEmissionOut(BaseModel):
    year: int
    pollutant: str
    name: str
    kg: float


class FacilityOut(BaseModel):
    id: int
    nima: str
    name: str
    activity: str | None
    location: LocationOut | None
    municipality: MunicipalityOut
    emissions: list[FacilityEmissionOut]


@router.get("/facilities/points", responses=INVALID_REQUEST)
def facility_points(
    session: SessionDep,
    pollutant: PollutantParam,
    year: YearParam,
) -> list[list[float]]:
    """[lon, lat, kg] of each facility that declared the pollutant in the year, the biggest
    emitter first. The year has to be one that has ended and not earlier than the first year
    with data."""
    refuse_year_out_of_range(year, session)
    # TODO: add Index(pollutant_code, year) to FacilityEmission in packages/db when the
    # register grows: the primary key (facility_id, pollutant_code, year) cannot serve
    # this lookup, so today it reads the whole table (fine at ~1,700 rows).
    rows = session.execute(
        select(func.ST_X(Facility.geom), func.ST_Y(Facility.geom), FacilityEmission.amount_kg)
        .join(FacilityEmission, FacilityEmission.facility_id == Facility.id)
        .where(
            FacilityEmission.pollutant_code == pollutant,
            FacilityEmission.year == year,
            Facility.geom.is_not(None),
        )
        .order_by(FacilityEmission.amount_kg.desc(), Facility.id)
    )
    return [[lon, lat, float(kg)] for lon, lat, kg in rows]


# This route has to come after /facilities/points, or "points" would be taken as an id.
@router.get("/facilities/{facility_id}", responses={**INVALID_REQUEST, **NOT_FOUND})
def facility_card(
    session: SessionDep, facility_id: Annotated[int, Path(ge=1, le=INTEGER_MAX)]
) -> FacilityOut:
    """The facility, its municipality and every emission it declared, the latest year
    first and, inside a year, the biggest amount first."""
    row = session.execute(
        select(Facility, Municipality, func.ST_X(Facility.geom), func.ST_Y(Facility.geom))
        .join(Municipality, Municipality.ine_code == Facility.municipality_code)
        .where(Facility.id == facility_id)
    ).one_or_none()
    if row is None:
        raise StarletteHTTPException(404, f"Facility {facility_id} not found.")
    facility, municipality, lon, lat = row
    emissions = session.execute(
        select(FacilityEmission, Pollutant.name)
        .join(Pollutant, Pollutant.code == FacilityEmission.pollutant_code)
        .where(FacilityEmission.facility_id == facility_id)
        .order_by(
            FacilityEmission.year.desc(),
            FacilityEmission.amount_kg.desc(),
            FacilityEmission.pollutant_code,
        )
    )
    return FacilityOut(
        id=facility.id,
        nima=facility.nima,
        name=facility.name,
        activity=facility.activity,
        location=None if lon is None else LocationOut(lon=lon, lat=lat),
        municipality=MunicipalityOut(code=municipality.ine_code, name=municipality.name),
        emissions=[
            FacilityEmissionOut(year=e.year, pollutant=e.pollutant_code, name=name, kg=e.amount_kg)
            for e, name in emissions
        ],
    )
