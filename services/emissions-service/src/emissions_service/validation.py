"""The parameters that more than one route takes: a pollutant code and a year."""

from datetime import date
from typing import Annotated

from aireuskadi_db import FacilityEmission
from fastapi import Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# The codes of core.pollutant: capitals, digits and underscore, up to the 20 of the column.
POLLUTANT_CODE = r"^[A-Z0-9_]+$"

PollutantParam = Annotated[str, Query(max_length=20, pattern=POLLUTANT_CODE)]
YearParam = Annotated[int, Query(ge=1)]


def refuse_year_out_of_range(year: int, session: Session) -> None:
    """A year that has not ended yet, or is earlier than the first one with emissions, has no
    data to ask for: refuse it with a 422 instead of answering an empty list."""
    last = date.today().year - 1
    if year > last:
        problem = {"type": "less_than_equal", "msg": f"Input should be at most {last}"}
    else:
        # Only now is the database asked: a year that has not ended needs no query to refuse.
        first = session.scalar(select(func.min(FacilityEmission.year)))
        if first is None or year >= first:
            return
        problem = {"type": "greater_than_equal", "msg": f"Input should be at least {first}"}
    raise RequestValidationError([{**problem, "loc": ("query", "year"), "input": year}])
