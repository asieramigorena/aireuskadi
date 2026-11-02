"""Basque E-PRTR register (aire_eprtr.csv): validates and cleans the rows before loading."""

import csv
import io
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Emission:
    nima: str  # id
    pollutant_code: str
    amount_kg: float
    x: float  # coordinates
    y: float
    row_number: int
    facility_name: str
    activity: str
    year: int


@dataclass(frozen=True)
class RejectedRow:
    row_number: int
    nima: str
    reason: str


@dataclass
class ParseResult:
    accepted: list[Emission] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    rows_read: int = 0


REQUIRED_COLUMNS = (
    "NIMA",
    "Denominación Centro",
    "CNAE 2009",
    "Datos del año",
    "XETRS89",
    "YETRS89",
    "Contaminante",
    "Cantidad (Kg/año)",
)


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _problem(row: dict[str, str]) -> str | None:
    """Why the row cannot be loaded, or None if it can."""
    x, y = _number(row["XETRS89"]), _number(row["YETRS89"])
    if x is None or y is None:
        return "coordinates are missing or not numbers"
    if x == 0 and y == 0:
        return "coordinates are 0,0 (not located)"
    if _number(row["Cantidad (Kg/año)"]) is None:
        return "amount is missing or not a number"
    if not row["Datos del año"].strip().isdigit():
        return "data year is missing or not a number"
    return None


REPEATED = "repeated facility and pollutant: a larger amount of the same pair is kept"


def _reject(result: ParseResult, row_number: int, nima: str, reason: str) -> None:
    result.rejected.append(RejectedRow(row_number, nima, reason))
    log.warning(
        "row rejected",
        extra={"source": "eprtr_air", "row_number": row_number, "nima": nima, "reason": reason},
    )


def parse_rows(text: str) -> ParseResult:
    result = ParseResult()
    largest: dict[tuple[str, str], Emission] = {}  # for multiple appearances
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"E-PRTR file is missing the columns: {', '.join(missing)}")
    for row_number, row in enumerate(reader, start=2):  # line 1 is the header
        result.rows_read += 1
        reason = _problem(row)
        if reason:
            _reject(result, row_number, row["NIMA"], reason)
            continue
        emission = Emission(
            row["NIMA"],
            row["Contaminante"],
            float(row["Cantidad (Kg/año)"]),
            float(row["XETRS89"]),
            float(row["YETRS89"]),
            row_number,
            row["Denominación Centro"],
            row["CNAE 2009"],
            int(row["Datos del año"]),
        )
        # The register repeats a facility and pollutant with different amounts and nothing to
        # tell them apart: keep the largest and reject the others, so every row is accounted for.
        key = (emission.nima, emission.pollutant_code)
        kept = largest.get(key)
        if kept is None:
            largest[key] = emission
        elif emission.amount_kg > kept.amount_kg:
            _reject(result, kept.row_number, kept.nima, REPEATED)
            largest[key] = emission
        else:
            _reject(result, emission.row_number, emission.nima, REPEATED)
    result.accepted = list(largest.values())
    return result
