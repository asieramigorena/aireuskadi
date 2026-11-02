"""Stations of the Basque air quality network (api.euskadi.eus/air-quality/stations)."""

import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StationRecord:
    code: str  # id in the network
    name: str
    municipality_code: str  # INE code: countyId + municipalityId
    longitude: float
    latitude: float


@dataclass(frozen=True)
class RejectedStation:
    code: str
    reason: str


@dataclass
class StationsResult:
    accepted: list[StationRecord] = field(default_factory=list)
    rejected: list[RejectedStation] = field(default_factory=list)


def _problem(properties: dict, geometry: dict | None) -> str | None:
    """Why the station cannot be loaded, or None if it can."""
    location = properties.get("location") or {}
    if not properties.get("id"):
        return "id is missing"
    if not (location.get("countyId") and location.get("municipalityId")):
        return "municipality is missing (countyId + municipalityId)"
    if not geometry or len(geometry.get("coordinates") or []) != 2:
        return "position is missing"
    return None


def parse_stations(text: str) -> StationsResult:
    result = StationsResult()
    document = json.loads(text)
    if not isinstance(document, dict) or "features" not in document:
        raise ValueError("the stations document has no `features`: the format of the API changed?")
    for feature in document["features"]:
        properties = feature["properties"]
        reason = _problem(properties, feature.get("geometry"))
        if reason:
            code = properties.get("id") or ""
            result.rejected.append(RejectedStation(code, reason))
            log.warning(
                "station rejected",
                extra={"source": "stations", "station": code, "reason": reason},
            )
            continue
        location = properties["location"]
        longitude, latitude = feature["geometry"]["coordinates"]
        result.accepted.append(
            StationRecord(
                properties["id"],
                properties["name"],
                location["countyId"] + location["municipalityId"],
                longitude,
                latitude,
            )
        )
    return result
