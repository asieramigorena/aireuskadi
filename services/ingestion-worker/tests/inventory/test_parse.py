import re

import pytest
from fakes import inventory_files, with_cell
from ingestion_worker.inventory.parse import InventoryRow, LayoutChanged, parse_inventory


def rows_of(rows, classification, pollutant=None):
    return [
        r
        for r in rows
        if r.classification == classification and pollutant in (None, r.pollutant_code)
    ]


def test_a_snap_sector_gives_one_row_per_year_with_its_pollutant_and_code():
    files = inventory_files(snap={"2.1": [["01", "Combustión ", 10.5, 9.0]]})

    rows = parse_inventory(*files, edition=1991)

    assert rows_of(rows, "SNAP", "SOX") == [
        InventoryRow("SOX", "SNAP", "01", "Combustión", 1990, 10.5),
        InventoryRow("SOX", "SNAP", "01", "Combustión", 1991, 9.0),
    ]
    # The sheets are the pollutants in their order: 2.6 is the total of particles, 2.8 is PM2,5.
    assert {r.pollutant_code for r in rows_of(rows, "SNAP")} == {
        "SOX",
        "NH3",
        "NOX",
        "NMVOC",
        "CO",
        "TSP",
        "PM10",
        "PM25",
    }


def test_a_sector_that_is_zero_in_every_year_is_left_out():
    files = inventory_files(
        snap={"2.1": [["01", "Combustión", 1.0, 1.0], ["05", "Extracción", 0, 0]]}
    )

    rows = parse_inventory(*files, edition=1991)

    assert {r.sector_code for r in rows_of(rows, "SNAP", "SOX")} == {"01"}


def test_nfr_keeps_the_first_level_and_the_row_without_code_and_leaves_out_the_subsectors():
    nh3 = [
        [1, "Energía", 5.0, 5.0],
        ["1A", "Combustibles", 5.0, 5.0],
        [None, "Sin correspondencia SNAP", 2.0, 2.0],
    ]
    files = inventory_files(nfr={"3.2": nh3}, totals={"3.2": [7.0, 7.0]})

    rows = parse_inventory(*files, edition=1991)

    assert {(r.sector_code, r.sector_name) for r in rows_of(rows, "NFR", "NH3")} == {
        ("1", "Energía"),
        ("NA", "Sin correspondencia SNAP"),
    }


def test_ch4_comes_from_the_totals_sheet_as_one_total_sector():
    rows = parse_inventory(*inventory_files(), edition=1991)

    assert rows_of(rows, "TOTAL") == [
        InventoryRow("CH4", "TOTAL", "TOTAL", "Total", 1990, 2.0),
        InventoryRow("CH4", "TOTAL", "TOTAL", "Total", 1991, 2.0),
    ]


def test_snap_sectors_that_do_not_add_up_to_the_total_abort():
    files = inventory_files(totals={"2.3": [100.0, 1.0]})

    with pytest.raises(LayoutChanged, match=r"2\.3"):
        parse_inventory(*files, edition=1991)


def test_a_missing_sheet_aborts():
    with pytest.raises(LayoutChanged, match=r"2\.8"):
        parse_inventory(*inventory_files(missing=("2.8",)), edition=1991)


def test_a_header_that_does_not_end_in_the_edition_year_aborts():
    with pytest.raises(LayoutChanged, match="years"):
        parse_inventory(*inventory_files(edition=1991), edition=1992)


@pytest.mark.parametrize("cell", [None, "-"])
def test_a_value_that_is_not_a_number_aborts(cell):
    files = inventory_files(
        snap={"2.1": [["01", "Combustión", cell, 1.0]]}, totals={"2.1": [1.0, 1.0]}
    )

    with pytest.raises(LayoutChanged, match=r"2\.1"):
        parse_inventory(*files, edition=1991)


def test_each_sheet_is_its_pollutant_so_the_total_of_particles_and_pm25_are_not_swapped():
    files = inventory_files(
        snap={"2.6": [["01", "Combustión", 6.0, 6.0]], "2.8": [["01", "Combustión", 8.0, 8.0]]},
        nfr={"3.6": [[1, "Energía", 6.0, 6.0]], "3.8": [[1, "Energía", 8.0, 8.0]]},
    )

    rows = parse_inventory(*files, edition=1991)

    values = {(r.classification, r.pollutant_code): r.value for r in rows if r.year == 1990}
    assert (values[("SNAP", "TSP")], values[("SNAP", "PM25")]) == (6.0, 8.0)
    assert (values[("NFR", "TSP")], values[("NFR", "PM25")]) == (6.0, 8.0)


@pytest.mark.parametrize("sheet", ["2.3", "3.3"])
def test_a_sheet_without_its_total_row_aborts(sheet):
    files = inventory_files(missing_total=(sheet,))

    with pytest.raises(LayoutChanged, match=re.escape(sheet)):
        parse_inventory(*files, edition=1991)


def test_a_totals_sheet_without_methane_aborts():
    with pytest.raises(LayoutChanged, match="CH4"):
        parse_inventory(*inventory_files(methane=False), edition=1991)


def test_a_value_that_is_infinite_aborts():
    # 1E999 is read as infinity: with the total infinite too, inf - inf is NaN and NaN is never
    # more than the tolerance, so the check of the sum alone would let it through.
    capv, snap, nfr = inventory_files(snap={"2.1": [["01", "Combustión", 777.5, 1.0]]})
    snap = with_cell(snap, "<v>777.5</v>", "<v>1E999</v>")

    with pytest.raises(LayoutChanged, match=r"2\.1"):
        parse_inventory(capv, snap, nfr, edition=1991)


def test_a_sector_that_comes_twice_aborts():
    twice = [["01", "Combustión", 1.0, 1.0], ["01", "Combustión", 1.0, 1.0]]
    files = inventory_files(snap={"2.1": twice})

    with pytest.raises(LayoutChanged, match=r"2\.1"):
        parse_inventory(*files, edition=1991)


def test_an_nfr_sheet_without_any_first_level_sector_aborts():
    files = inventory_files(nfr={"3.1": [["1A", "Combustibles", 1.0, 1.0]]})

    with pytest.raises(LayoutChanged, match=r"3\.1"):
        parse_inventory(*files, edition=1991)


def test_a_file_that_cannot_be_read_aborts_without_saying_what_is_in_it():
    capv, _, nfr = inventory_files()

    with pytest.raises(LayoutChanged) as error:
        parse_inventory(capv, b"not a workbook: secret text", nfr, edition=1991)

    assert "secret" not in str(error.value)


def test_a_file_that_unpacks_to_too_much_aborts(monkeypatch):
    monkeypatch.setattr("ingestion_worker.inventory.parse.MAX_UNPACKED_BYTES", 1000)

    with pytest.raises(LayoutChanged, match="too big"):
        parse_inventory(*inventory_files(), edition=1991)
