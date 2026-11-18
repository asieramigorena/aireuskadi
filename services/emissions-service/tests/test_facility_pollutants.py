"""GET /facilities/pollutants: the pollutants that have emissions in the register, for the picker of
the map."""


def test_only_the_pollutants_with_emissions_come_once_each_with_their_name(
    client, add_pollutant, add_facility
):
    add_pollutant("TSTA", "Test pollutant A")
    add_pollutant("TSTB", "Test pollutant B")
    add_pollutant("TSTC", "Test pollutant without emissions")
    add_facility("T000000001", -2.9, 43.2, [("TSTB", 2020, 1.0), ("TSTA", 2021, 2.0)])
    add_facility("T000000002", -2.8, 43.1, [("TSTA", 2020, 3.0)])

    response = client.get("/facilities/pollutants")

    assert response.status_code == 200
    ours = [p for p in response.json() if p["code"].startswith("TST")]
    assert ours == [
        {"code": "TSTA", "name": "Test pollutant A"},
        {"code": "TSTB", "name": "Test pollutant B"},
    ]
