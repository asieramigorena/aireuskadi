from datetime import UTC, datetime, timedelta

from ingestion_worker.measurements.run import measurements_hours

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def test_the_window_is_48_hours_the_first_time_and_when_the_last_success_is_recent():
    assert measurements_hours(NOW, None) == 48
    assert measurements_hours(NOW, NOW - timedelta(hours=1)) == 48


def test_after_a_long_stop_the_window_grows_to_cover_the_gap_with_three_hours_of_margin():
    assert measurements_hours(NOW, NOW - timedelta(hours=100)) == 103
    assert measurements_hours(NOW, NOW - timedelta(hours=100, minutes=1)) == 104  # rounded up


def test_the_window_never_goes_back_more_than_seven_days():
    assert measurements_hours(NOW, NOW - timedelta(days=30)) == 168
