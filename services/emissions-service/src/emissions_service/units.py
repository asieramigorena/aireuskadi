"""The urban units (municipalities, districts, territories) with their indicators for the map."""

import json
from typing import Annotated, Any, Literal

from aireuskadi_db import District, Municipality, Pollutant, Territory, unit_indicator
from aireuskadi_http import INVALID_REQUEST, NOT_FOUND
from fastapi import APIRouter, Path
from pydantic import BaseModel
from sqlalchemy import func, null, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from emissions_service.database import SessionDep
from emissions_service.validation import PollutantParam, YearParam, refuse_year_out_of_range

router = APIRouter()

# The licence of GeoEuskadi (CC BY 4.0) asks to credit the source of the boundaries and to say that
# they were changed ("simplified"). The service puts the text in the response, and the map only
# shows it, so that: (1) whoever draws these boundaries, the web client or any other client of the
# API, receives the credit together with the data and cannot use them without it; and (2) the
# wording lives in one place: if the licence asks for something else, only the service changes.
ATTRIBUTION = "GeoEuskadi / Gobierno Vasco, CC BY 4.0, simplified"


class UnitProperties(BaseModel):
    code: str
    name: str
    declared_t: float | None
    t_km2: float | None
    who_ratio: float | None


class UnitFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] | None
    properties: UnitProperties


class UnitCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    attribution: str = ATTRIBUTION
    features: list[UnitFeature]


def number(value):
    return None if value is None else float(value)


def indicators_of(pollutant, year):
    """The condition that joins a municipality with its indicators of the pollutant and the year."""
    return (
        (unit_indicator.c.municipality_code == Municipality.ine_code)
        & (unit_indicator.c.pollutant_code == pollutant)
        & (unit_indicator.c.year == year)
    )


def municipality_rows(pollutant, year):
    return (
        select(
            Municipality.ine_code,
            Municipality.name,
            func.ST_AsGeoJSON(Municipality.geom_simplified, 6),
            unit_indicator.c.declared_t,
            unit_indicator.c.t_km2,
            unit_indicator.c.who_ratio,
        )
        .outerjoin(unit_indicator, indicators_of(pollutant, year))
        .order_by(Municipality.ine_code)
    )


def grouped_rows(unit, pollutant, year):
    """A district or a territory: the tonnes of its municipalities added up and divided by the
    area of ALL of them (adding the densities, or taking their mean, would give another number).
    Nothing declared in any of them is null, not zero. The ratio with the WHO guideline is only
    for municipalities (issue #33)."""
    query = select(
        unit.code,
        unit.name,
        func.ST_AsGeoJSON(unit.geom_simplified, 6),
        func.sum(unit_indicator.c.declared_t),
        func.sum(unit_indicator.c.declared_t) / func.nullif(func.sum(Municipality.area_km2), 0),
        null(),
    ).select_from(unit)
    if unit is Territory:
        query = query.join(District, District.territory_code == Territory.code).join(
            Municipality, Municipality.district_code == District.code
        )
    else:
        query = query.join(Municipality, Municipality.district_code == District.code)
    return (
        query.outerjoin(unit_indicator, indicators_of(pollutant, year))
        .group_by(unit.code)
        .order_by(unit.code)
    )


@router.get("/units", responses=INVALID_REQUEST)
def units(
    session: SessionDep,
    level: Literal["municipality", "district", "territory"],
    pollutant: PollutantParam,
    year: YearParam,
) -> UnitCollection:
    """Every unit of the level as a GeoJSON feature: its simplified boundary and, for the
    pollutant and the year, the tonnes declared, the tonnes per km2 and the ratio with the WHO
    guideline. A unit without data for them is there with nulls. The year has to be one that has
    ended and not earlier than the first year with data."""
    refuse_year_out_of_range(year, session)
    if level == "municipality":
        query = municipality_rows(pollutant, year)
    else:
        query = grouped_rows(District if level == "district" else Territory, pollutant, year)
    return UnitCollection(
        features=[
            UnitFeature(
                geometry=None if geometry is None else json.loads(geometry),
                properties=UnitProperties(
                    code=code,
                    name=name,
                    declared_t=number(declared),
                    t_km2=number(density),
                    who_ratio=number(ratio),
                ),
            )
            for code, name, geometry, declared, density, ratio in session.execute(query)
        ]
    )


# The code of a territory has 2 digits, the one of a district 4 and the one of a municipality 5.
UNIT_CODE = r"^([0-9]{2}|[0-9]{4}|[0-9]{5})$"
LEVEL_OF_LENGTH = {2: "territory", 4: "district", 5: "municipality"}


class UnitReference(BaseModel):
    code: str
    name: str


class UnitEmission(BaseModel):
    year: int
    pollutant: str
    name: str
    declared_t: float | None
    t_km2: float | None
    who_ratio: float | None


class UnitCard(BaseModel):
    code: str
    level: Literal["municipality", "district", "territory"]
    name: str
    area_km2: float
    district: UnitReference | None
    territory: UnitReference | None
    emissions: list[UnitEmission]


def find_unit(session, code):
    """(name, district, territory) of the unit and the condition that selects its municipalities,
    or None when there is no such unit."""
    match LEVEL_OF_LENGTH[len(code)]:
        case "municipality":
            row = session.execute(
                select(
                    Municipality.name, District.code, District.name, Territory.code, Territory.name
                )
                .join(District, District.code == Municipality.district_code)
                .join(Territory, Territory.code == District.territory_code)
                .where(Municipality.ine_code == code)
            ).one_or_none()
            if row is None:
                return None
            name, district_code, district_name, territory_code, territory_name = row
            return (
                name,
                UnitReference(code=district_code, name=district_name),
                UnitReference(code=territory_code, name=territory_name),
                Municipality.ine_code == code,
            )
        case "district":
            row = session.execute(
                select(District.name, Territory.code, Territory.name)
                .join(Territory, Territory.code == District.territory_code)
                .where(District.code == code)
            ).one_or_none()
            if row is None:
                return None
            name, territory_code, territory_name = row
            return (
                name,
                None,
                UnitReference(code=territory_code, name=territory_name),
                Municipality.district_code == code,
            )
        case _:
            name = session.scalar(select(Territory.name).where(Territory.code == code))
            if name is None:
                return None
            return (name, None, None, District.territory_code == code)


@router.get("/units/{code}", responses={**INVALID_REQUEST, **NOT_FOUND})
def unit_card(session: SessionDep, code: Annotated[str, Path(pattern=UNIT_CODE)]) -> UnitCard:
    """The unit, where it is, its area and what was declared in it, the latest year first and,
    inside a year, the biggest amount first. A district or a territory adds up its municipalities;
    the ratio with the WHO guideline is only for a municipality."""
    found = find_unit(session, code)
    if found is None:
        raise StarletteHTTPException(404, f"Unit {code} not found.")
    name, district, territory, inside = found
    level = LEVEL_OF_LENGTH[len(code)]
    area = session.scalar(
        select(func.sum(Municipality.area_km2))
        .select_from(Municipality)
        .join(District, District.code == Municipality.district_code)
        .where(inside)
    )
    declared = func.sum(unit_indicator.c.declared_t)
    rows = session.execute(
        select(
            unit_indicator.c.year,
            unit_indicator.c.pollutant_code,
            Pollutant.name,
            declared,
            func.max(unit_indicator.c.who_ratio),
        )
        .select_from(unit_indicator)
        .join(Municipality, Municipality.ine_code == unit_indicator.c.municipality_code)
        .join(District, District.code == Municipality.district_code)
        .join(Pollutant, Pollutant.code == unit_indicator.c.pollutant_code)
        .where(inside)
        .group_by(unit_indicator.c.year, unit_indicator.c.pollutant_code, Pollutant.name)
        .order_by(
            unit_indicator.c.year.desc(),
            declared.desc().nulls_last(),
            unit_indicator.c.pollutant_code,
        )
    )
    return UnitCard(
        code=code,
        level=level,
        name=name,
        area_km2=float(area),
        district=district,
        territory=territory,
        emissions=[
            UnitEmission(
                year=year,
                pollutant=pollutant,
                name=pollutant_name,
                declared_t=number(total),
                t_km2=None if total is None else float(total / area),
                who_ratio=number(ratio) if level == "municipality" else None,
            )
            for year, pollutant, pollutant_name, total, ratio in rows
        ],
    )
