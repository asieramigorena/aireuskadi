"""Places each emission in the municipality whose boundary contains its point."""

import logging
from dataclasses import dataclass, field

import geopandas as gpd

from ingestion_worker.eprtr import Emission, RejectedRow

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocatedEmission:
    emission: Emission
    ine_code: str
    longitude: float
    latitude: float


@dataclass
class LocateResult:
    located: list[LocatedEmission] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)


def locate(emissions: list[Emission], municipalities: gpd.GeoDataFrame) -> LocateResult:
    """Municipalities need the columns `ine_code` and `geometry`, both in EPSG:25830."""
    if municipalities.empty:
        # Otherwise every row would be rejected as "outside" and the run would look successful.
        raise ValueError("there are no municipalities: load the boundaries first")
    points = gpd.GeoDataFrame(
        {"position": range(len(emissions))},
        geometry=gpd.points_from_xy([e.x for e in emissions], [e.y for e in emissions]),
        crs=municipalities.crs,
    )
    # `intersects` keeps points on a boundary; such a point matches two municipalities, so keep
    # the lowest INE code to give the same answer every time.
    joined = points.sjoin(municipalities[["ine_code", "geometry"]], predicate="intersects")
    joined = joined.sort_values(["position", "ine_code"]).drop_duplicates("position")
    degrees = joined.geometry.to_crs("EPSG:4326")
    result = LocateResult()
    found = set()
    for position, ine_code, point in zip(
        joined["position"], joined["ine_code"], degrees, strict=True
    ):
        result.located.append(LocatedEmission(emissions[position], ine_code, point.x, point.y))
        found.add(position)
    for position, emission in enumerate(emissions):
        if position in found:
            continue
        reason = "point is outside every municipality"
        result.rejected.append(RejectedRow(emission.row_number, emission.nima, reason))
        log.warning(
            "row rejected",
            extra={
                "source": "eprtr_air",
                "row_number": emission.row_number,
                "nima": emission.nima,
                "reason": reason,
            },
        )
    return result
