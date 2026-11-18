"""Reads the three files of the inventory that bring something new (the rest is derived):

- 2_ECA_SNAP: one sheet per pollutant, its 11 SNAP sectors and their total.
- 3_ECA_NFR: the same pollutants by NFR sector. Only the first level (codes 1 to 6 and the row
  without a code) is kept: below it the sectors do not add up to the one above.
- 1_ECA_CAPV: sheet 1.1 has the total of each substance; only methane (CH4) is new.

A row that is 0 in every year says nothing and is left out. If the layout is not the expected
one the whole file is refused (LayoutChanged), so that nothing half read reaches the database.
"""

import math
import zipfile
from dataclasses import dataclass
from io import BytesIO

from openpyxl import load_workbook

FIRST_YEAR = 1990
TOLERANCE = 0.01  # tonnes: the sectors of a SNAP sheet must add up to its total
# The real files are about 100 KB and their sheets 50 rows by 37 columns: far more than that is
# not the inventory, and reading it could take the memory of the machine.
MAX_UNPACKED_BYTES = 50 * 1024 * 1024
MAX_ROWS = 500
MAX_COLUMNS = 60
# The sheets are the pollutants in this order in both files.
SNAP_SHEETS = {"2.1": "SOX", "2.2": "NH3", "2.3": "NOX", "2.4": "NMVOC",
               "2.5": "CO", "2.6": "TSP", "2.7": "PM10", "2.8": "PM25"}  # fmt: skip
NFR_SHEETS = {"3.1": "SOX", "3.2": "NH3", "3.3": "NOX", "3.4": "NMVOC",
              "3.5": "CO", "3.6": "TSP", "3.7": "PM10", "3.8": "PM25"}  # fmt: skip


@dataclass(frozen=True)
class InventoryRow:
    pollutant_code: str
    classification: str  # SNAP, NFR or TOTAL
    sector_code: str
    sector_name: str
    year: int
    value: float  # tonnes, as published


class LayoutChanged(ValueError):
    """The file is not laid out as expected: nothing of it is loaded."""


def parse_inventory(capv: bytes, snap: bytes, nfr: bytes, edition: int) -> list[InventoryRow]:
    snap_sheets = _sheets(snap, "2_ECA_SNAP", list(SNAP_SHEETS))
    nfr_sheets = _sheets(nfr, "3_ECA_NFR", list(NFR_SHEETS))
    capv_sheets = _sheets(capv, "1_ECA_CAPV", ["1.1"])
    rows = []
    for sheet, pollutant in SNAP_SHEETS.items():
        rows += _snap_sheet(snap_sheets[sheet], sheet, pollutant, edition)
    for sheet, pollutant in NFR_SHEETS.items():
        rows += _nfr_sheet(nfr_sheets[sheet], sheet, pollutant, edition)
    rows += _methane(capv_sheets["1.1"], edition)
    return rows


def _sheets(data: bytes, file: str, names: list[str]) -> dict[str, list[tuple]]:
    """The rows of each sheet of `names` in the file. What goes wrong while reading is said by
    its kind only: the message of the library can quote the contents of the file."""
    try:
        if (
            sum(item.file_size for item in zipfile.ZipFile(BytesIO(data)).infolist())
            > MAX_UNPACKED_BYTES
        ):
            raise LayoutChanged(f"{file}: the file is too big")
        book = load_workbook(BytesIO(data), read_only=True, data_only=True)
        sheets = {}
        for name in names:
            if name not in book.sheetnames:
                raise LayoutChanged(f"{file}: sheet {name} is missing")
            cells = book[name].iter_rows(values_only=True, max_row=MAX_ROWS, max_col=MAX_COLUMNS)
            # Empty rows are dropped: they separate the parts of the report.
            sheets[name] = [row for row in cells if any(row)]
        book.close()
    except LayoutChanged:
        raise
    except Exception as error:  # noqa: BLE001 - whatever the library raises, the file is refused
        raise LayoutChanged(f"{file}: the file cannot be read ({type(error).__name__})") from None
    return sheets


def _years(rows: list[tuple], sheet: str, edition: int) -> tuple[int, dict[int, int]]:
    """Where the header is, and the column of each year in it."""
    for index, row in enumerate(rows):
        if FIRST_YEAR in row:
            columns = {column: value for column, value in enumerate(row) if type(value) is int}
            if list(columns.values()) != list(range(FIRST_YEAR, edition + 1)):
                raise LayoutChanged(f"sheet {sheet}: the years are not {FIRST_YEAR}-{edition}")
            return index, columns
    raise LayoutChanged(f"sheet {sheet}: no row with the years")


def _numbers(row: tuple, columns: dict[int, int], sheet: str) -> list[float]:
    values = [row[column] if column < len(row) else None for column in columns]
    for value in values:
        # Infinity and NaN are floats too, and NaN would pass the check of the sum.
        if type(value) not in (int, float) or not math.isfinite(value):
            raise LayoutChanged(f"sheet {sheet}: a value is not a number")
    return values


def _is_total(row: tuple) -> bool:
    return str(row[0] or "").startswith("Total")


def _rows_of(pollutant, classification, code, name, columns, values) -> list[InventoryRow]:
    """One row per year, or none if the sector is 0 in every year."""
    if all(value == 0 for value in values):
        return []
    return [
        InventoryRow(pollutant, classification, code, name, year, value)
        for year, value in zip(columns.values(), values, strict=True)
    ]


def _snap_sheet(rows, sheet, pollutant, edition) -> list[InventoryRow]:
    header, columns = _years(rows, sheet, edition)
    found, sums, codes = [], [0.0] * len(columns), set()
    for row in rows[header + 1 :]:
        if _is_total(row):
            total = _numbers(row, columns, sheet)
            for year_sum, year_total in zip(sums, total, strict=True):
                if abs(year_sum - year_total) > TOLERANCE:
                    raise LayoutChanged(f"sheet {sheet}: the sectors do not add up to the total")
            return found
        values = _numbers(row, columns, sheet)
        sums = [a + b for a, b in zip(sums, values, strict=True)]
        code, name = str(row[0]).strip(), str(row[1]).strip()
        _once(code, codes, sheet)
        found += _rows_of(pollutant, "SNAP", code, name, columns, values)
    raise LayoutChanged(f"sheet {sheet}: no total row")


def _nfr_sheet(rows, sheet, pollutant, edition) -> list[InventoryRow]:
    header, columns = _years(rows, sheet, edition)
    found, codes = [], set()
    for row in rows[header + 1 :]:
        if _is_total(row):
            # Codes 1 to 6 always come (most of them with numbers): none means another layout.
            if not codes - {"NA"}:
                raise LayoutChanged(f"sheet {sheet}: no sector of the first level")
            return found
        code = "NA" if row[0] is None else str(row[0]).strip()
        if len(code) == 1 or code == "NA":
            values = _numbers(row, columns, sheet)
            _once(code, codes, sheet)
            found += _rows_of(pollutant, "NFR", code, str(row[1]).strip(), columns, values)
    raise LayoutChanged(f"sheet {sheet}: no total row")


def _once(code: str, codes: set[str], sheet: str) -> None:
    """A sector that comes twice in a sheet is another layout (and two rows of the same key)."""
    if code in codes:
        raise LayoutChanged(f"sheet {sheet}: a sector comes twice")
    codes.add(code)


def _methane(rows, edition) -> list[InventoryRow]:
    header, columns = _years(rows, "1.1", edition)
    for row in rows[header + 1 :]:
        if str(row[0] or "").startswith("CH4"):
            values = _numbers(row, columns, "1.1")
            return _rows_of("CH4", "TOTAL", "TOTAL", "Total", columns, values)
    raise LayoutChanged("sheet 1.1: no CH4 row")
