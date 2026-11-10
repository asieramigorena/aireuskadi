import json

import pytest
from ingestion_worker.measurements.stations import parse_stations


def feature(
    code="83", name="ELCIEGO", county="01", municipality="022", coordinates=(-2.6195, 42.5182)
):
    """A station as the GeoJSON of https://api.euskadi.eus/air-quality/stations has it."""
    properties = {
        "id": code,
        "name": name,
        "location": {"countyId": county, "municipalityId": municipality},
    }
    if coordinates is None:
        return {"type": "Feature", "geometry": None, "properties": properties}
    geometry = {"type": "Point", "coordinates": list(coordinates)}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def collection(*features):
    return json.dumps({"type": "FeatureCollection", "features": list(features)})


def test_a_station_has_its_code_name_ine_code_of_the_municipality_and_position():
    result = parse_stations(collection(feature()))

    (station,) = result.accepted
    assert (station.code, station.name) == ("83", "ELCIEGO")
    assert station.municipality_code == "01022"  # countyId 01 + municipalityId 022
    assert (station.longitude, station.latitude) == (-2.6195, 42.5182)  # GeoJSON is [lon, lat]


def test_a_station_without_position_municipality_or_id_is_rejected_logged_and_the_others_stay(
    caplog,
):
    no_position = feature(code="1", coordinates=None)
    no_municipality = feature(code="2", municipality="")
    no_id = feature(code="")
    good = feature(code="83")

    with caplog.at_level("WARNING", logger="ingestion_worker.measurements.stations"):
        result = parse_stations(collection(no_position, no_municipality, no_id, good))

    assert [s.code for s in result.accepted] == ["83"]
    assert [(r.code, r.reason.split()[0]) for r in result.rejected] == [
        ("1", "position"),
        ("2", "municipality"),
        ("", "id"),
    ]
    assert len(caplog.records) == 3
    assert {r.getMessage() for r in caplog.records} == {"station rejected"}
    assert {r.source for r in caplog.records} == {"stations"}


def test_a_document_that_is_not_a_feature_collection_is_refused_with_a_clear_message():
    with pytest.raises(ValueError, match="features"):
        parse_stations(json.dumps({"message": "service unavailable"}))
