"""run_eprtr against a real PostgreSQL + PostGIS. Skipped without DATABASE_URL.

A run commits, because the view can only be refreshed after the commit. The fixture deletes
what the tests write: the test municipality 99001 and its facilities, and the runs.
"""

import hashlib
from datetime import date

import pytest
from aireuskadi_db import IngestionRun
from ingestion_worker.run_eprtr import run_eprtr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

HEADER = (
    "Año declaración;Datos del año;CIF/DNI;Razón Social/Nombre;NIMA;Denominación Centro;"
    "Provincia;Municipio;30-UTM30;XETRS89;YETRS89;CNAE 2009;Medio receptor;Contaminante;"
    "Descripción;Cantidad (Kg/año);Cantidad accidental (Kg/año)"
)


def csv_row(nima, x, y, pollutant, amount):
    return (
        f"2024;2023;X;Someone;{nima};FACTORY {nima};Araba/Álava;Town;30 - UTM30;{x};{y};"
        f"0146 - Pigs;Aire;{pollutant};D;{amount};"
    )


# The test municipality is the square X 495000-505000, Y 4700000-4710000 (EPSG:25830).
FILE = "\r\n".join(
    [
        HEADER,
        csv_row("T000000001", "500000.0", "4705000.0", "030402", "5000.0"),  # loaded
        csv_row("T000000002", "0.0", "0.0", "030402", "1.0"),  # coordinates 0,0
        csv_row("T000000003", "500000.0", "4900000.0", "030402", "1.0"),  # outside
        csv_row("T000000004", "500000.0", "4705000.0", "999999", "1.0"),  # unknown pollutant
    ]
).encode("utf-8-sig")


CATALOG_URL = (
    "https://opendata.euskadi.eus/catalogo/-/"
    "registro-de-emisiones-y-transferencias-de-contaminantes-del-2023-prtr/"
)
CATALOG_PAGE = b"<li>Fecha de actualizaci&#243;n <b>28/09/2026</b></li>"


def test_a_successful_run_loads_the_file_records_its_counts_and_refreshes_the_view(
    engine, boundaries
):
    urls = []

    def fetch(url):
        urls.append(url)
        return CATALOG_PAGE if url == CATALOG_URL else FILE

    run_eprtr(engine, 2023, fetch=fetch)

    expected = (
        "https://opendata.euskadi.eus/contenidos/ds_registros/e_prtr_euskadi_2023/opendata/"
        "aire_eprtr.csv"
    )
    assert urls == [expected, CATALOG_URL]
    with Session(engine) as session:
        run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()
        assert (run.source, run.status, run.error) == ("eprtr_air", "succeeded", None)
        assert run.source_url == expected
        assert run.source_updated_at == date(2026, 9, 28)
        assert run.file_hash == hashlib.sha256(FILE).hexdigest()
        assert (run.rows_read, run.rows_loaded, run.rows_rejected) == (4, 1, 3)
        assert run.finished_at is not None
        declared_t = session.scalar(
            text(
                "SELECT declared_t FROM core.unit_indicator "
                "WHERE municipality_code = '99001' AND pollutant_code = 'NOX' AND year = 2023"
            )
        )
        assert float(declared_t) == 5.0  # 5000 kg


def last_run(engine):
    with Session(engine) as session:
        return session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())).first()


def test_a_failed_download_marks_the_run_as_failed_loads_nothing_and_raises(engine, boundaries):
    def fetch(url):
        raise RuntimeError("the server is down")

    with pytest.raises(RuntimeError, match="the server is down"):
        run_eprtr(engine, 2023, fetch=fetch)

    run = last_run(engine)
    assert (run.source, run.status) == ("eprtr_air", "failed")
    assert "the server is down" in run.error
    assert run.finished_at is not None
    assert (run.rows_read, run.rows_loaded, run.rows_rejected) == (0, 0, 0)
    with engine.connect() as conn:
        assert (
            conn.scalar(text("SELECT count(*) FROM core.facility WHERE nima LIKE 'T0000000%'")) == 0
        )


def test_if_the_database_refuses_a_row_halfway_nothing_of_the_file_stays(engine, boundaries):
    # 1e20 kg fits a float but not NUMERIC(18,3): the error comes after the facilities are
    # inserted, so this checks that they are rolled back with it.
    absurd = "\r\n".join(
        [
            HEADER,
            csv_row("T000000001", "500000.0", "4705000.0", "030402", "5000.0"),
            csv_row("T000000002", "500000.0", "4705000.0", "030402", "1e20"),
        ]
    ).encode("utf-8-sig")

    with pytest.raises(Exception, match="numeric"):
        run_eprtr(engine, 2023, fetch=lambda url: absurd)

    assert last_run(engine).status == "failed"
    with engine.connect() as conn:
        assert (
            conn.scalar(text("SELECT count(*) FROM core.facility WHERE nima LIKE 'T0000000%'")) == 0
        )


def test_if_the_catalog_page_cannot_be_read_the_run_still_succeeds_without_the_date(
    engine, boundaries, caplog
):
    def fetch(url):
        if url == CATALOG_URL:
            raise RuntimeError("the catalog is down")
        return FILE

    with caplog.at_level("WARNING", logger="ingestion_worker.run_eprtr"):
        run_eprtr(engine, 2023, fetch=fetch)

    run = last_run(engine)
    assert (run.status, run.source_updated_at) == ("succeeded", None)
    (record,) = [r for r in caplog.records if r.getMessage() == "source update date not available"]
    assert record.levelname == "WARNING"
    assert "the catalog is down" in record.reason
