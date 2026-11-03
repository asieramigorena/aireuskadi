"""GET /pollutants: the catalogue with the WHO guideline values."""


def test_pollutants_lists_the_catalogue_with_its_who_guidelines(client, add_pollutant):
    add_pollutant(
        "TSTA",
        "Test pollutant A",
        group="Test group",
        guidelines=[("annual", 2021, "15.000"), ("24h", 2021, "45.000")],
    )
    add_pollutant("TSTB", "Test pollutant B")

    response = client.get("/pollutants")

    assert response.status_code == 200
    by_code = {item["code"]: item for item in response.json()}
    assert by_code["TSTA"]["name"] == "Test pollutant A"
    assert by_code["TSTA"]["group"] == "Test group"
    assert sorted(by_code["TSTA"]["who_guidelines"], key=lambda g: g["averaging_period"]) == [
        {"averaging_period": "24h", "edition": 2021, "value_ugm3": 45.0},
        {"averaging_period": "annual", "edition": 2021, "value_ugm3": 15.0},
    ]
    # A pollutant without a guideline is still in the catalogue, with an empty list.
    assert by_code["TSTB"]["who_guidelines"] == []
