from ingestion_worker.eprtr.years import years_to_load


def published(*years):
    """`exists` for a register that has published these years."""
    return lambda year: year in years


def test_with_nothing_loaded_it_takes_the_latest_year_that_exists():
    assert years_to_load(None, published(2022, 2023), this_year=2026) == [2023]


def test_with_nothing_loaded_and_nothing_published_there_is_nothing_to_load():
    assert years_to_load(None, published(), this_year=2026) == []


def test_the_year_already_loaded_is_loaded_again_because_the_register_corrects_it():
    assert years_to_load(2023, published(2023), this_year=2026) == [2023]


def test_every_new_year_that_has_been_published_is_loaded_in_order():
    assert years_to_load(2023, published(2023, 2024, 2025), this_year=2026) == [2023, 2024, 2025]


def test_it_never_asks_for_a_year_that_has_not_started_even_if_the_source_says_yes():
    asked = []

    def always(year):
        asked.append(year)
        return True

    assert years_to_load(2023, always, this_year=2026) == [2023, 2024, 2025, 2026]
    assert max(asked) == 2026
