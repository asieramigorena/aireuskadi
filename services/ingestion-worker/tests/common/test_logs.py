import io
import json
import logging
import sys
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


def crash(monkeypatch, capsys, exception):
    """What the standard output holds after `exception` goes uncaught, once logging is set up."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # put back when the test ends
    try:
        configure_logging()
        try:
            raise exception
        except BaseException:  # noqa: BLE001 - this is what the interpreter does with it
            sys.excepthook(*sys.exc_info())
        return capsys.readouterr().out
    finally:
        root.handlers[:], root.level = handlers, level


def test_a_crash_is_one_json_line_with_its_traceback_not_a_dozen_lines_of_plain_text(
    monkeypatch, capsys
):
    out = crash(monkeypatch, capsys, RuntimeError("the server is down"))

    (line,) = out.splitlines()
    entry = json.loads(line)
    assert (entry["level"], entry["message"]) == ("CRITICAL", "uncaught exception")
    assert "Traceback" in entry["exception"]
    assert "RuntimeError: the server is down" in entry["exception"]


def test_stopping_the_program_with_ctrl_c_is_not_logged_as_a_critical_failure(monkeypatch, capsys):
    assert crash(monkeypatch, capsys, KeyboardInterrupt()) == ""
