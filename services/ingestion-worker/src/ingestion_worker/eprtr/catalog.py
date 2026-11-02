"""The catalog page of a dataset in Open Data Euskadi: when it was last updated.

The legal notice of Open Data Euskadi asks to give the date of the last update of the data.
"""

import html
import re
from datetime import date

# "." instead of the accented letter: the page is not UTF-8 and the letter can arrive broken.
_UPDATED = re.compile(r"Fecha de actualizaci.n\s*(\d{2})/(\d{2})/(\d{4})")


def catalog_updated_at(page: str) -> date | None:
    """The "Fecha de actualización" of the page, or None if it is not there or not a real date."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    match = _UPDATED.search(re.sub(r"\s+", " ", text))
    if match is None:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None
