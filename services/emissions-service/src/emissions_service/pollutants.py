"""The catalogue of pollutants with their WHO guideline values."""

from aireuskadi_db import Pollutant, WhoGuideline
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from emissions_service.database import SessionDep

router = APIRouter()


class GuidelineOut(BaseModel):
    averaging_period: str
    edition: int
    value_ugm3: float


class PollutantOut(BaseModel):
    code: str
    name: str
    group: str | None
    who_guidelines: list[GuidelineOut]


@router.get("/pollutants")
def pollutants(session: SessionDep) -> list[PollutantOut]:
    rows = session.scalars(select(Pollutant).order_by(Pollutant.code)).all()
    guidelines: dict[str, list[GuidelineOut]] = {}
    for g in session.scalars(select(WhoGuideline)):
        guidelines.setdefault(g.pollutant_code, []).append(
            GuidelineOut(
                averaging_period=g.averaging_period,
                edition=g.edition,
                value_ugm3=g.value_ugm3,
            )
        )
    return [
        PollutantOut(
            code=p.code,
            name=p.name,
            group=p.group,
            who_guidelines=guidelines.get(p.code, []),
        )
        for p in rows
    ]
