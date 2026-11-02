"""run_boundaries against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL (conftest)."""

import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from aireuskadi_db import IngestionRun, Municipality
from ingestion_worker.run_boundaries import run_boundaries
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.orm import Session

SQUARE = box(495_000, 4_700_000, 505_000, 4_710_000)


def shapefile_zip(**columns) -> bytes:
    """A zipped shapefile in EPSG:25830, like the ones GeoEuskadi publishes."""
    rows = len(next(iter(columns.values())))
    layer = gpd.GeoDataFrame(columns, geometry=[SQUARE] * rows, crs="EPSG:25830")
    with tempfile.TemporaryDirectory() as folder:
        layer.to_file(Path(folder) / "layer.shp")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in Path(folder).iterdir():
                archive.write(path, path.name)
    return buffer.getvalue()


LAYERS = {
    "TERRITORIOS": shapefile_zip(TERRITORIO=["TEST"], PRO_PROV=["99"]),
    "COMARCAS": shapefile_zip(COMARCA=["TEST DISTRICT"], COM_PROV=["99"], COM_COM=["01"]),
    "MUNICIPIOS": shapefile_zip(
        NOMBRE_TOP=["Testville", "Some mancomunidad"],
        EUSTAT=["99001", "99501"],
        MUN_PROV=["99", "99"],
        MUN_COMR=["01", "01"],
        MUN_MUNI=["001", "501"],  # 500-799 is not a municipality
    ),
}


def fetch(url: str) -> bytes:
    return next(data for name, data in LAYERS.items() if f"/{name}_5000_ETRS89.zip" in url)


def test_a_run_downloads_the_three_layers_loads_the_municipalities_and_records_the_counts(engine):
    run_boundaries(engine, fetch=fetch)

    with Session(engine) as session:
        run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        assert (run.source, run.status, run.error) == ("boundaries", "succeeded", None)
        assert (run.rows_read, run.rows_loaded, run.rows_rejected) == (2, 1, 1)
        assert run.file_hash is not None and len(run.file_hash) == 64
        assert [
            m.name
            for m in session.scalars(select(Municipality).where(Municipality.ine_code.like("99%")))
        ] == ["Testville"]
