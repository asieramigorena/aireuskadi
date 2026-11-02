import geopandas as gpd
from ingestion_worker.boundaries.layers import (
    district_records,
    municipality_records,
    select_municipalities,
    territory_records,
)
from shapely.geometry import box


def layer(*rows: tuple[str, str, str]) -> gpd.GeoDataFrame:
    """Rows are (MUN_MUNI, NOMBRE_TOP, EUSTAT), as in MUNICIPIOS_5000_ETRS89."""
    return gpd.GeoDataFrame(
        {
            "MUN_MUNI": [r[0] for r in rows],
            "NOMBRE_TOP": [r[1] for r in rows],
            "EUSTAT": [r[2] for r in rows],
        },
        geometry=[box(i * 1000, 0, i * 1000 + 1000, 1000) for i in range(len(rows))],
        crs="EPSG:25830",
    )


def test_only_real_municipalities_are_kept_not_mancomunidades_or_parzonerias():
    boundaries = layer(
        ("002", "Amurrio", "01002"),  # an ordinary municipality
        ("501", "Parzoneria General de Gipuzkoa y Bizkaia", "20501"),  # 500-799: not a municipality
        ("799", "Mancomunidad X", "48799"),
        ("902", "Erandio", "48902"),  # 800 and above are municipalities too (INE codes 9xx)
    )

    kept = select_municipalities(boundaries)

    assert list(kept["EUSTAT"]) == ["01002", "48902"]


def test_limitadua_is_dropped_even_though_it_carries_the_code_of_a_real_municipality():
    # In the real layer this polygon is listed under Aramaio's code (01003) and Otxandio's (48072).
    boundaries = layer(
        ("003", "Aramaio", "01003"),
        ("003", "Limitadua / El Limitado", "01003"),
        ("072", "Otxandio", "48072"),
        ("072", "Limitadua / El Limitado", "48072"),
    )

    kept = select_municipalities(boundaries)

    assert list(kept["NOMBRE_TOP"]) == ["Aramaio", "Otxandio"]


def test_the_area_is_in_square_kilometres_computed_in_metres():
    # 10 km x 10 km square in EPSG:25830 (metres): 100 km2 by geometry.
    square = gpd.GeoDataFrame(
        {
            "MUN_MUNI": ["002"],
            "NOMBRE_TOP": ["Amurrio"],
            "EUSTAT": ["01002"],
            "MUN_PROV": ["01"],
            "MUN_COMR": ["06"],
        },
        geometry=[box(500_000, 4_700_000, 510_000, 4_710_000)],
        crs="EPSG:25830",
    )

    (record,) = municipality_records(square).itertuples()

    assert abs(record.area_km2 - 100.0) < 0.001


def test_the_geometry_is_a_multipolygon_in_degrees():
    # Square centred on X = 500000, the central meridian of UTM zone 30 (3 degrees west).
    square = layer(("002", "Amurrio", "01002")).assign(
        MUN_PROV="01", MUN_COMR="06", geometry=[box(495_000, 4_700_000, 505_000, 4_710_000)]
    )

    records = municipality_records(square)

    (geometry,) = records.geometry
    assert records.crs == "EPSG:4326"
    assert geometry.geom_type == "MultiPolygon"
    assert abs(geometry.centroid.x - (-3.0)) < 1e-4


def test_records_carry_the_ine_code_the_name_and_a_district_code_that_includes_the_province():
    # Comarca number 01 exists in all three territories: the code must tell them apart.
    towns = layer(
        ("002", "Amurrio", "01002"),
        ("001", "Hondarribia", "20036"),
    ).assign(MUN_PROV=["01", "20"], MUN_COMR=["01", "01"])

    records = municipality_records(towns)

    assert [(r.ine_code, r.name, r.district_code) for r in records.itertuples()] == [
        ("01002", "Amurrio", "0101"),
        ("20036", "Hondarribia", "2001"),
    ]


def test_a_territory_is_identified_by_its_province_code():
    territories = gpd.GeoDataFrame(
        {"TERRITORIO": ["ARABA / ÁLAVA", "BIZKAIA"], "PRO_PROV": ["01", "48"]},
        geometry=[box(0, 0, 1000, 1000), box(2000, 0, 3000, 1000)],
        crs="EPSG:25830",
    )

    records = territory_records(territories)

    assert [(r.code, r.name) for r in records.itertuples()] == [
        ("01", "ARABA / ÁLAVA"),
        ("48", "BIZKAIA"),
    ]
    assert records.geometry.iloc[0].geom_type == "MultiPolygon"


def test_a_district_code_is_province_plus_comarca_and_points_to_its_territory():
    districts = gpd.GeoDataFrame(
        {
            "COMARCA": ["AÑANA", "ARRATIA-NERVIÓN"],
            "COM_PROV": ["01", "48"],
            "COM_COM": ["01", "01"],
        },
        geometry=[box(0, 0, 1000, 1000), box(2000, 0, 3000, 1000)],
        crs="EPSG:25830",
    )

    records = district_records(districts)

    assert [(r.code, r.territory_code, r.name) for r in records.itertuples()] == [
        ("0101", "01", "AÑANA"),
        ("4801", "48", "ARRATIA-NERVIÓN"),
    ]
