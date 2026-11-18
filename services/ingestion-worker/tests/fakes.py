"""Downloads that tests use instead of the network: what the sources would return.

The loaders take a function `fetch(url) -> bytes`; these are the files it gives back.
"""

import io
import json
import random
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, box

# --- E-PRTR register (aire_eprtr.csv)

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


# --- GeoEuskadi boundaries (three zipped shapefiles)

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


# --- Air quality network (stations and hourly measurements)

API = "https://api.euskadi.eus/air-quality"

# The test station is in the test municipality 99001: countyId 99 + municipalityId 001.
STATIONS = json.dumps(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-3.0, 42.5]},
                "properties": {
                    "id": "T-1",
                    "name": "TEST STATION",
                    "location": {"countyId": "99", "municipalityId": "001"},
                },
            }
        ],
    }
)


def hour(date, *measurements, real=True):
    station = {"id": "T-1", "name": "TEST STATION", "measurements": list(measurements)}
    if real:
        station["airQualityStation"] = "Buena"
    return {"date": date, "station": [station]}


COUNTY_48 = json.dumps(
    [
        hour(
            "2026-11-02T12:00:00Z",
            {"name": "NO2", "value": 18.0, "unit": "µg/m3", "airquality": "Buena"},
            {"name": "CO", "value": 0.4, "unit": "mg/m3"},
            {"name": "Mercurio", "value": 0.1, "unit": "ng/m3"},  # not a known pollutant
            {"name": "V.vien", "value": 3.2, "unit": "m/s"},  # weather
        ),
        hour("2026-11-02T13:00:00Z", {"name": "NO2", "value": 0.0, "unit": "µg/m3"}, real=False),
    ]
)


def fake_fetch(requested=None):
    pages = {f"{API}/stations": STATIONS}
    for county in ("01", "20"):
        pages[county] = "[]"
    pages["48"] = COUNTY_48

    def fetch(url):
        if requested is not None:
            requested.append(url)
        for key, body in pages.items():
            if url == key or (key in ("01", "20", "48") and f"/counties/{key}/" in url):
                return body.encode()
        raise AssertionError(f"unexpected url {url}")

    return fetch


# --- Boundaries with a border that wiggles

X0, Y0, Y1 = 500_000, 4_780_000, 4_783_000


def wiggly_pair(misaligned_by: float = 0.0) -> gpd.GeoDataFrame:
    """Two municipalities (EPSG:25830) that share a border of 300 vertices that wiggles by up to
    60 m, more than the tolerance, so that simplifying each one on its own would not agree.

    The real layer is not a perfect coverage: the two sides of a border differ by a few centimetres.
    `misaligned_by` moves each vertex of the east copy of the border by up to that many metres.
    """
    rng = random.Random(7)
    border = [(X0 + rng.uniform(-60, 60), Y0 + i * 10) for i in range(301)]
    other = random.Random(8)
    east_border = [
        (
            x + other.uniform(-misaligned_by, misaligned_by),
            y + other.uniform(-misaligned_by, misaligned_by),
        )
        for x, y in border
    ]
    west = Polygon([(X0 - 3000, Y0), (X0 - 3000, Y1), *reversed(border)])
    east = Polygon([(X0 + 3000, Y1), (X0 + 3000, Y0), *east_border])
    return gpd.GeoDataFrame(
        {
            "EUSTAT": ["99001", "99002"],
            "NOMBRE_TOP": ["West", "East"],
            "MUN_PROV": ["99", "99"],
            "MUN_COMR": ["01", "01"],
        },
        geometry=[west, east],
        crs="EPSG:25830",
    )


# --- Inventory of emissions 1990-<edition> (1_ECA_CAPV, 2_ECA_SNAP, 3_ECA_NFR)


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    """A workbook with one sheet per key and those rows in it."""
    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    data = io.BytesIO()
    book.save(data)
    return data.getvalue()


def with_cell(data: bytes, old: str, new: str) -> bytes:
    """The workbook with the XML of a value replaced, to write what openpyxl would not
    (e.g. `1E999`, which is read back as infinity)."""
    source = zipfile.ZipFile(io.BytesIO(data))
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as target:
        for item in source.infolist():
            content = source.read(item)
            if item.filename.startswith("xl/worksheets/"):
                content = content.replace(old.encode(), new.encode())
            target.writestr(item, content)
    return result.getvalue()


def report_sheet(
    head: list, rows: list[list], years: list[int], total: list | None, with_total: bool = True
) -> list[list]:
    """A sheet laid out like the real ones: title, units, header with the years, the rows, the
    total of the rows (or the one given) and the source."""
    columns = len(head)
    if total is None:
        total = [sum(row[columns + i] for row in rows) for i in range(len(years))]
    total_row = ["Total emisiones. C.A. de Euskadi", *([None] * (columns - 1)), *total]
    return [
        ["Evolución de las emisiones"],
        ["C.A de Euskadi. 1990-...."],
        ["Unidades: toneladas"],
        [*head, *years],
        *rows,
        *([total_row] if with_total else []),
        ["Fuente: Gobierno Vasco."],
    ]


def inventory_files(
    edition: int = 1991,
    years: list[int] | None = None,
    snap: dict[str, list[list]] | None = None,
    nfr: dict[str, list[list]] | None = None,
    totals: dict[str, list] | None = None,
    missing: tuple[str, ...] = (),
    missing_total: tuple[str, ...] = (),
    methane: bool = True,
) -> tuple[bytes, bytes, bytes]:
    """The three files of an edition. Every SNAP sheet has sector 01 and every NFR sheet sector 1
    unless `snap`/`nfr` give other rows for a sheet; `totals` replaces the total of a sheet;
    `missing` leaves sheets out, `missing_total` their total row, `methane=False` the CH4 row."""
    years = years or list(range(1990, edition + 1))
    ones = [1.0] * len(years)
    snap, nfr, totals = snap or {}, nfr or {}, totals or {}

    def book(names, head, default, given):
        sheets = {"Índice": [["Índice"]]}
        for name in names:
            if name not in missing:
                rows = given.get(name, [default])
                with_total = name not in missing_total
                sheets[name] = report_sheet(head, rows, years, totals.get(name), with_total)
        return xlsx(sheets)

    snap_book = book(
        [f"2.{i}" for i in range(1, 9)],
        ["Código \nSNAP", "Descripción SNAP"],
        ["01", "Combustión en la producción de energía", *ones],
        snap,
    )
    nfr_book = book(
        [f"3.{i}" for i in range(1, 9)],
        ["Código NFR para CRLTAP\nSNAP(*)", "Descripción NFR para CRLTAP"],
        [1, "Energía", *ones],
        nfr,
    )
    capv_rows = [
        ["Emisiones PROT por sustancia"],
        ["NOX: Óxidos de nitrógeno", *ones],
        *([["CH4: Metano ", *[2.0] * len(years)]] if methane else []),
    ]
    capv_book = xlsx(
        {
            "Índice": [["Índice"]],
            "1.1": [
                ["1.1.- Evolución"],
                ["Unidades: toneladas"],
                ["Sustancia", *years],
                *capv_rows,
            ],
            "1.2": [["Unidades: toneladas equivalentes"]],
            "1.3": [["Unidades: Índice base 1990=100"]],
        }
    )
    return capv_book, snap_book, nfr_book


def inventory_fetch(files: tuple[bytes, bytes, bytes], year: int = 1991):
    """A fetch that gives the three files of the edition `year` and refuses any other url."""
    from ingestion_worker.inventory.run import FILES, file_url

    pages = {file_url(name, year): data for name, data in zip(FILES, files, strict=True)}

    def fetch(url):
        if url not in pages:
            raise AssertionError(f"unexpected url {url}")
        return pages[url]

    return fetch
