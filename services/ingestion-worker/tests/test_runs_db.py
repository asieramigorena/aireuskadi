"""The log lines of track_run. Skipped without DATABASE_URL (see conftest.py).

The Grafana dashboard "Ingestion" counts these messages: "run finished" and "run failed".
"""

import pytest
from ingestion_worker.runs import track_run

LOGGER = "ingestion_worker.runs"


def records(caplog, message):
    return [r for r in caplog.records if r.getMessage() == message]


def test_a_finished_run_is_logged_with_its_source_and_counts(engine, caplog):
    def work(session, run):
        run.rows_read, run.rows_loaded, run.rows_rejected = 10, 7, 3

    with caplog.at_level("INFO", logger=LOGGER):
        track_run(engine, "test_source", "http://example.test/file.csv", work)

    (record,) = records(caplog, "run finished")
    assert record.levelname == "INFO"
    assert (record.source, record.rows_read, record.rows_loaded, record.rows_rejected) == (
        "test_source",
        10,
        7,
        3,
    )


def test_a_failed_run_is_logged_as_an_error_with_the_exception_and_still_raises(engine, caplog):
    def work(session, run):
        raise RuntimeError("the server is down")

    with caplog.at_level("INFO", logger=LOGGER), pytest.raises(RuntimeError):
        track_run(engine, "test_source", "http://example.test/file.csv", work)

    assert records(caplog, "run finished") == []
    (record,) = records(caplog, "run failed")
    assert record.levelname == "ERROR"
    assert (record.source, record.error) == ("test_source", "the server is down")
    assert record.exc_info is not None  # the traceback goes to the "exception" field of the JSON
