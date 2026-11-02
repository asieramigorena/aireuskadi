from datetime import date

from ingestion_worker.eprtr.catalog import catalog_updated_at

# What the catalog page of Open Data Euskadi shows, reduced: the creation date comes first.
PAGE = (
    "<li><span>Fecha de creaci&#243;n</span> <b>20/03/2025</b></li>"
    "<li><span>Fecha de actualizaci&#243;n</span> <b>28/09/2026</b></li>"
    "<li><span>Fecha de inicio de datos</span> <b>01/01/2023</b></li>"
)


def test_the_update_date_is_read_and_not_the_creation_date():
    assert catalog_updated_at(PAGE) == date(2026, 9, 28)


def test_a_page_whose_accent_arrived_broken_is_still_read():
    # The real page is not UTF-8: decoded as UTF-8 the accent becomes U+FFFD.
    assert catalog_updated_at(PAGE.replace("&#243;", "�")) == date(2026, 9, 28)


def test_a_page_without_the_label_gives_none():
    assert catalog_updated_at("<html>Fecha de creaci&#243;n 20/03/2025</html>") is None


def test_an_impossible_date_gives_none_instead_of_failing():
    assert catalog_updated_at("Fecha de actualizaci&#243;n 31/02/2026") is None
