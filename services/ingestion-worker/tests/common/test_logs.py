import io
import json
import logging
from decimal import Decimal

import pytest
from ingestion_worker.common.logs import JsonFormatter, configure_logging


@pytest.fixture
def lines():
    """Logger that writes through JsonFormatter into a buffer; returns the parsed lines."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test_logs")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield lambda: [json.loads(line) for line in buffer.getvalue().splitlines()]
    logger.handlers.clear()


def test_a_line_is_a_json_object_with_the_extra_fields(lines):
    logging.getLogger("test_logs").warning(
        "row rejected", extra={"source": "eprtr_air", "row_number": 12, "reason": "no coordinates"}
    )

    (entry,) = lines()
    assert entry["level"] == "WARNING"
    assert entry["logger"] == "test_logs"
    assert entry["message"] == "row rejected"
    assert entry["time"].endswith("+00:00")
    assert (entry["source"], entry["row_number"], entry["reason"]) == (
        "eprtr_air",
        12,
        "no coordinates",
    )


def test_an_extra_field_never_replaces_a_standard_one(lines):
    logging.getLogger("test_logs").info("loaded", extra={"level": "chatty", "time": "yesterday"})

    (entry,) = lines()
    assert entry["level"] == "INFO"
    assert entry["extra_level"] == "chatty"
    assert entry["extra_time"] == "yesterday"


def test_accents_and_values_json_does_not_know_are_kept(lines):
    logging.getLogger("test_logs").info("Cerámica Marlo", extra={"amount_kg": Decimal("2122.56")})

    (entry,) = lines()
    assert entry["message"] == "Cerámica Marlo"
    assert entry["amount_kg"] == "2122.56"


def test_an_exception_goes_in_the_line(lines):
    try:
        raise ValueError("bad header")
    except ValueError:
        logging.getLogger("test_logs").exception("run failed")

    (entry,) = lines()
    assert "ValueError: bad header" in entry["exception"]


def test_the_level_comes_from_log_level(monkeypatch):
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        configure_logging()
        assert root.level == logging.DEBUG
        monkeypatch.delenv("LOG_LEVEL")
        configure_logging()
        assert root.level == logging.INFO
    finally:
        root.handlers[:], root.level = handlers, level
