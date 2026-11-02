import pytest
from ingestion_worker.eprtr import parse_rows

# Header of the real file (aire_eprtr.csv, 2023 edition).
HEADER = (
    "Año declaración;Datos del año;CIF/DNI;Razón Social/Nombre;NIMA;Denominación Centro;"
    "Provincia;Municipio;30-UTM30;XETRS89;YETRS89;CNAE 2009;Medio receptor;Contaminante;"
    "Descripción;Cantidad (Kg/año);Cantidad accidental (Kg/año)"
)


def csv_text(*rows: str) -> str:
    return "\r\n".join([HEADER, *rows]) + "\r\n"


def row(
    nima="0100001585",
    name="GRANJA SAN MARTIN",
    x="508591.0",
    y="4722787.0",
    pollutant="030402",
    amount="5.56",
    year="2023",
):
    return (
        f"2024;{year};16433186P;Someone;{nima};{name};Araba/Álava;Zambrana;30 - UTM30;{x};{y};"
        f"0146 - Explotación de ganado porcino;Aire;{pollutant};X;{amount};"
    )


def test_a_row_at_coordinates_zero_is_rejected_with_its_reason():
    result = parse_rows(csv_text(row(name="METAL SMELTING LEGUTIO", x="0.0", y="0.0")))

    assert result.accepted == []
    (rejected,) = result.rejected
    assert rejected.row_number == 2  # line 1 is the header
    assert rejected.nima == "0100001585"
    assert "coordinates" in rejected.reason


def test_a_repeated_facility_and_pollutant_keeps_the_largest_amount():
    # The largest is in the middle, so "first" and "last" would both be wrong.
    result = parse_rows(
        csv_text(
            row(pollutant="030402", amount="100.0"),
            row(pollutant="030402", amount="900.5"),
            row(pollutant="030402", amount="300.0"),
        )
    )

    (emission,) = result.accepted
    assert emission.amount_kg == 900.5


def test_the_same_pollutant_in_two_facilities_is_not_merged():
    result = parse_rows(
        csv_text(
            row(nima="0100001585", pollutant="030402", amount="10.0"),
            row(nima="0100000202", pollutant="030402", amount="20.0"),
        )
    )

    assert {(e.nima, e.amount_kg) for e in result.accepted} == {
        ("0100001585", 10.0),
        ("0100000202", 20.0),
    }


def test_a_row_without_coordinates_is_rejected_and_the_others_are_kept():
    result = parse_rows(
        csv_text(
            row(nima="0100000001", x="", y=""),
            row(nima="0100000002"),
        )
    )

    assert [e.nima for e in result.accepted] == ["0100000002"]
    (rejected,) = result.rejected
    assert (rejected.row_number, rejected.nima) == (2, "0100000001")
    assert "coordinates" in rejected.reason


def test_a_row_with_an_unreadable_amount_is_rejected_and_the_others_are_kept():
    result = parse_rows(
        csv_text(
            row(nima="0100000001", amount="n/d"),
            row(nima="0100000002", amount=""),
            row(nima="0100000003"),
        )
    )

    assert [e.nima for e in result.accepted] == ["0100000003"]
    assert [(r.row_number, r.nima) for r in result.rejected] == [
        (2, "0100000001"),
        (3, "0100000002"),
    ]
    assert all("amount" in r.reason for r in result.rejected)


def test_a_file_without_a_required_column_is_refused_naming_the_column():
    renamed = csv_text(row()).replace("XETRS89", "X_ETRS89")

    with pytest.raises(ValueError, match="XETRS89"):
        parse_rows(renamed)


def test_every_rejected_row_is_logged_as_a_warning_with_its_reason(caplog):
    with caplog.at_level("WARNING", logger="ingestion_worker.eprtr"):
        parse_rows(csv_text(row(nima="0100000001", x="0.0", y="0.0"), row(nima="0100000002")))

    (record,) = caplog.records
    assert record.levelname == "WARNING"
    assert record.getMessage() == "row rejected"
    assert record.source == "eprtr_air"
    assert (record.row_number, record.nima) == (2, "0100000001")
    assert "0,0" in record.reason


def test_an_accepted_emission_remembers_the_csv_line_it_came_from():
    result = parse_rows(
        csv_text(
            row(nima="0100000001", x="0.0", y="0.0"),  # line 2, rejected
            row(nima="0100000002", pollutant="030402", amount="1.0"),  # line 3
            row(nima="0100000002", pollutant="030402", amount="5.0"),  # line 4, the largest
        )
    )

    (emission,) = result.accepted
    assert emission.row_number == 4


def test_an_emission_carries_the_facility_name_the_activity_and_the_data_year():
    # The file has two years: "Año declaración" (2024, when it was declared) and "Datos del año"
    # (2023, what the amounts are about). The amounts belong to the second.
    result = parse_rows(csv_text(row(name="GRANJA SAN MARTIN", year="2023")))

    (emission,) = result.accepted
    assert emission.facility_name == "GRANJA SAN MARTIN"
    assert emission.activity == "0146 - Explotación de ganado porcino"
    assert emission.year == 2023


def test_a_row_with_an_unreadable_data_year_is_rejected_and_the_others_are_kept():
    result = parse_rows(csv_text(row(nima="0100000001", year="20x3"), row(nima="0100000002")))

    assert [e.nima for e in result.accepted] == ["0100000002"]
    (rejected,) = result.rejected
    assert (rejected.row_number, rejected.nima) == (2, "0100000001")
    assert "year" in rejected.reason


def test_rows_read_counts_every_data_row_of_the_file():
    result = parse_rows(
        csv_text(
            row(nima="0100000001", x="0.0", y="0.0"),  # rejected
            row(nima="0100000002", amount="1.0"),  # repeated
            row(nima="0100000002", amount="2.0"),
            row(nima="0100000003"),
        )
    )

    assert result.rows_read == 4


def test_every_row_is_either_accepted_or_rejected_so_the_counts_add_up():
    result = parse_rows(
        csv_text(
            row(nima="0100000001", x="0.0", y="0.0"),  # rejected: coordinates
            row(nima="0100000002", amount="1.0"),  # rejected: repeated, a larger one follows
            row(nima="0100000002", amount="2.0"),
            row(nima="0100000003", amount="3.0"),  # rejected: repeated, a larger one came before
            row(nima="0100000003", amount="1.0"),
        )
    )

    assert len(result.accepted) + len(result.rejected) == result.rows_read


def test_a_repeated_row_that_is_left_out_is_rejected_with_its_line_and_logged(caplog):
    with caplog.at_level("WARNING", logger="ingestion_worker.eprtr"):
        result = parse_rows(
            csv_text(
                row(nima="0100000001", pollutant="030402", amount="100.0"),  # line 2: left out
                row(nima="0100000001", pollutant="030402", amount="900.5"),  # line 3: kept
                row(nima="0100000001", pollutant="030402", amount="300.0"),  # line 4: left out
            )
        )

    assert [e.row_number for e in result.accepted] == [3]
    assert [(r.row_number, r.nima) for r in result.rejected] == [
        (2, "0100000001"),
        (4, "0100000001"),
    ]
    assert all("repeated" in r.reason for r in result.rejected)
    assert sorted(r.row_number for r in caplog.records) == [2, 4]
    assert all(r.getMessage() == "row rejected" for r in caplog.records)
