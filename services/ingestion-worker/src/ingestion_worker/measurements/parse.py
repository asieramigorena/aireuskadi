"""Hourly measurements of the Basque air quality network (api.euskadi.eus/air-quality)."""

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeasurementRecord:
    station_code: str
    pollutant_code: str
    averaging_period: str  # 1h: the hourly value; 8h: running mean of 8 hours
    ts: datetime  # UTC
    value: float
    unit: str  # as published: µg/m3, mg/m3...


# Weather, not pollutants.
NOT_POLLUTANTS = frozenset({"D.vien", "H", "P", "R", "R.UVA", "Tº", "V.vien", "Precipitación"})
# What the API says about a value that was not measured; its value is a 0 that means nothing.
NO_DATA = "Sin datos"


@dataclass(frozen=True)
class RejectedValue:
    station_code: str
    ts: datetime
    name: str  # as the API calls it
    reason: str


@dataclass
class MeasurementsResult:
    accepted: list[MeasurementRecord] = field(default_factory=list)
    rejected: list[RejectedValue] = field(default_factory=list)
    skipped: int = 0  # values that are not data: placeholders, weather and "no data"

    @property
    def rows_read(self) -> int:
        """The values that were tried: the ones that are not data do not count."""
        return len(self.accepted) + len(self.rejected)


def _names() -> dict[str, tuple[str, str]]:
    """API name -> (pollutant code, averaging period), from data/api_names.csv."""
    text = (
        resources.files("ingestion_worker.measurements")
        .joinpath("data/api_names.csv")
        .read_text("utf-8")
    )
    return {
        row["api_name"]: (row["pollutant_code"], row["averaging_period"])
        for row in csv.DictReader(text.splitlines())
    }


def _reject(result: MeasurementsResult, station: str, ts: datetime, name: str, reason: str) -> None:
    result.rejected.append(RejectedValue(station, ts, name, reason))
    log.warning(
        "row rejected",
        extra={
            "source": "measurements",
            "station": station,
            "ts": ts.isoformat(),
            "pollutant_name": name,  # `name` is a reserved attribute of a log record
            "reason": reason,
        },
    )


def parse_measurements(text: str) -> MeasurementsResult:
    names = _names()
    result = MeasurementsResult()
    for hour in json.loads(text):
        ts = datetime.fromisoformat(hour["date"]).astimezone(UTC)
        for station in hour["station"]:
            # The hours that have not been measured yet come as zeros, without this qualification.
            placeholder = "airQualityStation" not in station
            for measurement in station["measurements"]:
                if (
                    placeholder
                    or measurement["name"] in NOT_POLLUTANTS
                    or measurement.get("airquality") == NO_DATA
                ):
                    result.skipped += 1
                    continue
                name = measurement["name"]
                if name not in names:
                    reason = f"pollutant name {name!r} is not known"
                    _reject(result, station["id"], ts, name, reason)
                    continue
                try:
                    value = float(measurement["value"])
                except (TypeError, ValueError):
                    _reject(result, station["id"], ts, name, "value is not a number")
                    continue
                pollutant, averaging = names[name]
                result.accepted.append(
                    MeasurementRecord(
                        station["id"], pollutant, averaging, ts, value, measurement["unit"]
                    )
                )
    return result
