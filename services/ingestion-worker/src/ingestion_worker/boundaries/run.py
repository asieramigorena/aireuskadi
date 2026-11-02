"""One run of the boundaries loader: territories, districts and municipalities of GeoEuskadi."""

import hashlib
import io
from collections.abc import Callable

import geopandas as gpd
from aireuskadi_db import IngestionRun
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ingestion_worker.boundaries.layers import (
    district_records,
    load_boundaries,
    municipality_records,
    select_municipalities,
    territory_records,
)
from ingestion_worker.common.download import download
from ingestion_worker.common.runs import track_run

SOURCE = "boundaries"
URL = "https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/{layer}_5000_ETRS89.zip"


def run_boundaries(engine: Engine, fetch: Callable[[str], bytes] = download) -> None:
    def work(session: Session, run: IngestionRun) -> None:
        zips = {
            layer: fetch(URL.format(layer=layer))
            for layer in ("TERRITORIOS", "COMARCAS", "MUNICIPIOS")
        }
        layers = {name: gpd.read_file(io.BytesIO(data)) for name, data in zips.items()}
        municipalities = select_municipalities(layers["MUNICIPIOS"])
        load_boundaries(
            session,
            territory_records(layers["TERRITORIOS"]),
            district_records(layers["COMARCAS"]),
            municipality_records(municipalities),
        )
        run.file_hash = hashlib.sha256(b"".join(zips[name] for name in sorted(zips))).hexdigest()
        run.rows_read = len(layers["MUNICIPIOS"])
        run.rows_loaded = len(municipalities)
        run.rows_rejected = run.rows_read - run.rows_loaded

    track_run(engine, SOURCE, URL.format(layer="*"), work)
