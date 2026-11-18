"""GET /facilities/years: the years of the register that have emissions, for the year picker."""


def test_the_years_with_emissions_come_once_each_from_the_oldest(
    client, add_pollutant, add_facility
):
    add_pollutant("TSTA", "Test pollutant A")
    add_facility("T000000001", -2.9, 43.2, [("TSTA", 1902, 1.0), ("TSTA", 1901, 2.0)])
    add_facility("T000000002", -2.8, 43.1, [("TSTA", 1902, 3.0)])

    response = client.get("/facilities/years")

    assert response.status_code == 200
    years = response.json()
    assert years == sorted(set(years))
    assert {1901, 1902} <= set(years)
