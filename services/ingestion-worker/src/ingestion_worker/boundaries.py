"""GeoEuskadi boundaries: territories, districts (comarcas) and municipalities."""

import geopandas as gpd
from aireuskadi_db import District, Municipality, Territory
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

SRID = 4326


def select_municipalities(boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keeps the real municipalities of the MUNICIPIOS layer.

    The layer also holds mancomunidades and parzonerias (MUN_MUNI 500-799) and a polygon called
    "Limitadua / El Limitado" that is listed twice, under the codes of Aramaio and Otxandio.
    Due to this issue, Limitadua is dropped.
    """
    code = boundaries["MUN_MUNI"].astype(int)
    is_limitadua = boundaries["NOMBRE_TOP"].str.startswith("Limitadua")
    return boundaries[((code < 500) | (code >= 800)) & ~is_limitadua]


def municipality_records(municipalities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The rows of core.municipality. Input in EPSG:25830, the layer as GeoEuskadi publishes it."""
    return gpd.GeoDataFrame(
        {
            "ine_code": municipalities["EUSTAT"],
            "name": municipalities["NOMBRE_TOP"],
            # The comarca number repeats in each territory, so the province goes first.
            "district_code": municipalities["MUN_PROV"] + municipalities["MUN_COMR"],
            "area_km2": municipalities.geometry.area / 1_000_000,  # metres squared -> km2
        },
        geometry=_to_degrees_multipolygon(municipalities.geometry),
    )


def territory_records(territories: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The rows of core.territory. The code is the INE province code."""
    return gpd.GeoDataFrame(
        {"code": territories["PRO_PROV"], "name": territories["TERRITORIO"]},
        geometry=_to_degrees_multipolygon(territories.geometry),
    )


def district_records(districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The rows of core.district. Same code as the district_code of the municipality records."""
    return gpd.GeoDataFrame(
        {
            "code": districts["COM_PROV"] + districts["COM_COM"],
            "territory_code": districts["COM_PROV"],
            "name": districts["COMARCA"],
        },
        geometry=_to_degrees_multipolygon(districts.geometry),
    )


def _to_degrees_multipolygon(geometry: gpd.GeoSeries) -> gpd.GeoSeries:
    """The columns are MULTIPOLYGON in EPSG:4326, and some areas are a single Polygon."""
    return geometry.to_crs("EPSG:4326").apply(
        lambda g: MultiPolygon([g]) if isinstance(g, Polygon) else g
    )


def load_boundaries(
    session: Session,
    territories: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    municipalities: gpd.GeoDataFrame,
) -> None:
    """Writes the three layers, parents first. Inserts new rows and updates existing ones.

    It does not commit: the caller owns the transaction, so a failure leaves nothing behind.
    """
    for model, records, key in (
        (Territory, territories, "code"),
        (District, districts, "code"),
        (Municipality, municipalities, "ine_code"),
    ):
        rows = [_row(record) for record in records.to_dict("records")]
        statement = insert(model).values(rows)
        update = {c: statement.excluded[c] for c in rows[0] if c != key}
        session.execute(statement.on_conflict_do_update(index_elements=[key], set_=update))


def _row(record: dict) -> dict:
    """A record of a *_records function as the columns of its table."""
    row = {name: value for name, value in record.items() if name != "geometry"}
    row["geom"] = from_shape(record["geometry"], srid=SRID)
    return row


def read_municipalities(session: Session) -> gpd.GeoDataFrame:
    """The municipalities in core, with the columns `ine_code` and `geometry` in EPSG:25830.

    The database keeps degrees; the E-PRTR coordinates are in metres, so locate() needs metres.
    """
    municipalities = gpd.read_postgis(
        "SELECT ine_code, geom FROM core.municipality",
        session.connection(),
        geom_col="geom",
        crs=f"EPSG:{SRID}",
    )
    return municipalities.rename_geometry("geometry").to_crs("EPSG:25830")
