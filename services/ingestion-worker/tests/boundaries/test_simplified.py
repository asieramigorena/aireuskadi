"""The simplified boundaries: a lighter geometry for the web map, computed for the whole layer."""

import geopandas as gpd
import shapely
import shapely.affinity
from fakes import wiggly_pair
from ingestion_worker.boundaries.layers import (
    district_records,
    municipality_records,
    territory_records,
)
from shapely.geometry import Polygon

X0, Y0 = 500_000, 4_780_000


def test_each_municipality_has_a_simplified_multipolygon_with_far_fewer_vertices():
    records = municipality_records(wiggly_pair())

    for original, simplified in zip(records.geometry, records["simplified"], strict=True):
        assert simplified.geom_type == "MultiPolygon"
        assert simplified.is_valid
        assert shapely.get_num_coordinates(simplified) < shapely.get_num_coordinates(original) / 5


def test_neighbours_still_share_their_border_with_no_gap_and_no_overlap():
    west, east = municipality_records(wiggly_pair())["simplified"]

    union = west.union(east)

    assert west.intersection(east).area < 1e-12  # no overlap
    assert union.geom_type == "Polygon"  # one piece: they touch along the whole border
    assert len(union.interiors) == 0  # and there is no hole between them
    assert abs(union.area - (west.area + east.area)) < 1e-12


def test_the_shape_is_kept_the_area_changes_by_less_than_one_per_cent():
    records = municipality_records(wiggly_pair())

    for original, simplified in zip(records.geometry, records["simplified"], strict=True):
        assert abs(simplified.area - original.area) / original.area < 0.01


def test_a_feature_bigger_than_the_tolerance_is_kept():
    # A 500 m square with a bump of 150 m x 150 m (9 % of its area). The tolerance is about 55 m,
    # so the bump has to stay; with a tolerance four times bigger it would be flattened.
    bump = Polygon(
        [
            (0, 0),
            (500, 0),
            (500, 175),
            (650, 175),
            (650, 325),
            (500, 325),
            (500, 500),
            (0, 500),
        ]
    )
    town = gpd.GeoDataFrame(
        {"EUSTAT": ["99001"], "NOMBRE_TOP": ["Bump"], "MUN_PROV": ["99"], "MUN_COMR": ["01"]},
        geometry=[shapely.affinity.translate(bump, X0, Y0)],
        crs="EPSG:25830",
    )

    records = municipality_records(town)

    (original,), (simplified,) = records.geometry, records["simplified"]
    assert abs(simplified.area - original.area) / original.area < 0.02


def test_districts_and_territories_are_simplified_too():
    layer = wiggly_pair()
    territories = layer.assign(PRO_PROV=["99", "98"], TERRITORIO=["West", "East"])
    districts = layer.assign(COM_PROV=["99", "98"], COM_COM=["01", "01"], COMARCA=["West", "East"])

    for records in (territory_records(territories), district_records(districts)):
        for original, simplified in zip(records.geometry, records["simplified"], strict=True):
            assert (
                shapely.get_num_coordinates(simplified) < shapely.get_num_coordinates(original) / 5
            )


def test_neighbours_whose_borders_differ_by_a_hair_still_get_no_overlap():
    # In the layer of GeoEuskadi, 121 of the 252 municipalities have an edge that does not match
    # the one of its neighbour, and then the simplifier draws each side on its own: 107 pairs
    # overlapped, up to 4 hectares. A difference of half a millimetre is enough to do that, and
    # snapping the vertices to a grid of about 10 cm first makes both sides agree again.
    west, east = municipality_records(wiggly_pair(misaligned_by=0.0005))["simplified"]

    overlap_m2 = west.intersection(east).area * 111_320 * 111_320 * 0.73

    assert overlap_m2 < 1.0
