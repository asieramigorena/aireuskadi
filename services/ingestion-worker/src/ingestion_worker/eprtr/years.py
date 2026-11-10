"""Which editions of the E-PRTR register to load: the URL has the year and a year does not exist
until the register publishes it."""

from collections.abc import Callable

from aireuskadi_db import FacilityEmission
from sqlalchemy import func, select
from sqlalchemy.orm import Session

LOOKBACK = 4  # with nothing loaded, how many years back to look for the latest edition


def years_to_load(
    latest_loaded: int | None, exists: Callable[[int], bool], this_year: int
) -> list[int]:
    """The years to load, in order.

    With nothing loaded, the latest edition that exists. Otherwise the year already loaded, which
    is loaded again because the register corrects its data, and every year after it that has been
    published. It never asks for a year after `this_year`.
    """
    if latest_loaded is None:
        for year in range(this_year, this_year - LOOKBACK - 1, -1):
            if exists(year):
                return [year]
        return []
    years = [latest_loaded]
    year = latest_loaded + 1
    while year <= this_year and exists(year):
        years.append(year)
        year += 1
    return years


def latest_loaded_year(session: Session) -> int | None:
    """The highest year that has emissions in core, or None if there are none."""
    return session.scalar(select(func.max(FacilityEmission.year)))
