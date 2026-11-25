"""GET /inventory: the yearly series of the inventory of the Basque Country, by sector."""

ROWS = [
    ("TSTA", "SNAP", "X02", 1990, 2.0),
    ("TSTA", "SNAP", "X01", 1991, 3.0),
    ("TSTA", "SNAP", "X01", 1990, 1.0),
    ("TSTA", "SNAP", "X01", 1992, 4.0),
    ("TSTA", "NFR", "X1", 1990, 4.0),
    ("TSTA", "NFR", "X2", 1990, 5.0),
]


def series(response):
    return [(p["sector"]["code"], p["year"], p["value"]) for p in response.json()["series"]]


def test_the_snap_series_of_a_pollutant_comes_by_sector_and_year(client, add_inventory):
    add_inventory(ROWS)

    response = client.get("/inventory?pollutant=TSTA")

    assert response.status_code == 200
    body = response.json()
    assert (body["pollutant"], body["unit"], body["classification"]) == ("TSTA", "t", "SNAP")
    assert "CC BY 4.0" in body["attribution"]
    assert series(response) == [
        ("X01", 1990, 1.0),
        ("X01", 1991, 3.0),
        ("X01", 1992, 4.0),
        ("X02", 1990, 2.0),
    ]
    assert body["series"][0]["sector"] == {"code": "X01", "name": "Sector X01"}


def test_one_sector_and_the_nfr_classification_can_be_chosen(client, add_inventory):
    add_inventory(ROWS)

    response = client.get("/inventory?pollutant=TSTA&classification=NFR&sector=X1")

    assert series(response) == [("X1", 1990, 4.0)]


def test_the_years_are_cut_by_from_and_to(client, add_inventory):
    add_inventory(ROWS)

    response = client.get("/inventory?pollutant=TSTA&from=1991&to=1991")

    assert series(response) == [("X01", 1991, 3.0)]


def test_a_selection_without_rows_is_a_404_problem(client, add_inventory):
    add_inventory(ROWS)

    response = client.get("/inventory?pollutant=TSTA&classification=TOTAL")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_a_classification_that_does_not_exist_is_a_422(client):
    response = client.get("/inventory?pollutant=TSTA&classification=XYZ")

    assert response.status_code == 422
