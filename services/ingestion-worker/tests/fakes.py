"""Downloads that tests use instead of the network: what the sources would return.

The loaders take a function `fetch(url) -> bytes`; these are the files it gives back.
"""

import io
import json
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

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
