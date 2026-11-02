import geopandas as gpd
import pytest
from ingestion_worker.eprtr import Emission
from ingestion_worker.locate import locate
from shapely.geometry import box

# Two neighbouring squares in EPSG:25830 metres. They stand for two municipalities.
MUNICIPALITIES = gpd.GeoDataFrame(
    {"ine_code": ["01059", "20069"]},
    geometry=[
        box(495_000, 4_700_000, 510_000, 4_710_000),
        box(510_000, 4_700_000, 520_000, 4_710_000),
    ],
    crs="EPSG:25830",
)


def emission(nima="0100000001", x=505_000.0, y=4_705_000.0, row_number=2):
    return Emission(nima, "030402", 1.0, x, y, row_number, "A facility", "0146 - Pigs", 2023)


def test_an_emission_gets_the_ine_code_of_the_municipality_that_contains_it():
    west = emission(nima="0100000001", x=505_000.0)
    east = emission(nima="2000000002", x=515_000.0)

    result = locate([west, east], MUNICIPALITIES)

    assert [(e.emission.nima, e.ine_code) for e in result.located] == [
        ("0100000001", "01059"),
        ("2000000002", "20069"),
    ]


def test_an_emission_outside_every_municipality_is_rejected_logged_and_the_others_are_kept(caplog):
    inside = emission(nima="0100000001", row_number=2)
    far_north = emission(nima="0100000002", y=4_700_000.0 + 255_000.0, row_number=3)  # bad Y

    with caplog.at_level("WARNING", logger="ingestion_worker.locate"):
        result = locate([inside, far_north], MUNICIPALITIES)

    assert [e.emission.nima for e in result.located] == ["0100000001"]
    (rejected,) = result.rejected
    assert (rejected.row_number, rejected.nima) == (3, "0100000002")
    assert "outside" in rejected.reason
    (record,) = caplog.records
    assert record.getMessage() == "row rejected"
    assert (record.source, record.row_number, record.nima) == ("eprtr_air", 3, "0100000002")


def test_a_located_emission_has_longitude_and_latitude_in_degrees():
    # X = 500000 is the central meridian of UTM zone 30, which is 3 degrees west by definition.
    # Y = 4705000 m north is near Vitoria-Gasteiz, about 42.5 degrees north.
    result = locate([emission(x=500_000.0, y=4_705_000.0)], MUNICIPALITIES)

    (located,) = result.located
    assert abs(located.longitude - (-3.0)) < 1e-6
    assert 42.4 < located.latitude < 42.6


def test_an_emission_exactly_on_a_shared_boundary_is_assigned_once_to_the_lowest_ine_code():
    on_the_border = emission(x=510_000.0)  # the edge shared by both squares

    result = locate([on_the_border], MUNICIPALITIES)

    assert result.rejected == []
    assert [e.ine_code for e in result.located] == ["01059"]


def test_without_municipalities_it_refuses_instead_of_rejecting_every_row():
    nothing = MUNICIPALITIES.iloc[0:0]

    with pytest.raises(ValueError, match="boundaries"):
        locate([emission()], nothing)
