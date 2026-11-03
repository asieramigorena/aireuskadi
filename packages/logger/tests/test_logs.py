"""JSON logging: one JSON object per line on standard output, for every service."""

import io
import json
import logging
import sys
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import NamedTuple

import pytest
from aireuskadi_logger import JsonFormatter, configure_logging


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


def test_accents_are_written_as_they_are_not_as_escape_codes():
    record = logging.makeLogRecord({"msg": "Cerámica Marlo", "name": "test_logs"})

    assert "Cerámica Marlo" in JsonFormatter().format(record)


def test_an_exception_goes_in_the_line(lines):
    try:
        raise ValueError("bad header")
    except ValueError:
        logging.getLogger("test_logs").exception("run failed")

    (entry,) = lines()
    assert "ValueError: bad header" in entry["exception"]


def test_a_configured_process_writes_json_lines_on_stdout(capsys):
    configure_logging("test_service")

    logging.getLogger("anything").info("hello", extra={"status": 200})

    (line,) = capsys.readouterr().out.splitlines()
    entry = json.loads(line)
    assert (entry["message"], entry["logger"], entry["status"]) == ("hello", "anything", 200)


def test_the_level_comes_from_log_level(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging("test_service")
    assert root.level == logging.DEBUG
    monkeypatch.delenv("LOG_LEVEL")
    configure_logging("test_service")
    assert root.level == logging.INFO


def crash(capsys, exception):
    """What the standard output holds after `exception` goes uncaught, once logging is set up."""
    configure_logging("test_service")
    try:
        raise exception
    except BaseException:  # noqa: BLE001 - this is what the interpreter does with it
        sys.excepthook(*sys.exc_info())
    return capsys.readouterr().out


def test_a_crash_is_one_json_line_with_its_traceback_not_a_dozen_lines_of_plain_text(capsys):
    out = crash(capsys, RuntimeError("the server is down"))

    (line,) = out.splitlines()
    entry = json.loads(line)
    assert (entry["level"], entry["message"]) == ("CRITICAL", "uncaught exception")
    assert entry["logger"] == "test_service"
    assert "Traceback" in entry["exception"]
    assert "RuntimeError: the server is down" in entry["exception"]


def test_stopping_the_program_with_ctrl_c_is_not_logged_as_a_critical_failure(capsys):
    assert crash(capsys, KeyboardInterrupt()) == ""


# Under uvicorn: it installs its own plain-text handlers before it loads the application.


def test_with_uvicorn_its_messages_also_come_out_as_json_and_only_once(capsys):
    uvicorn = logging.getLogger("uvicorn")
    uvicorn.addHandler(logging.StreamHandler())
    uvicorn.propagate = False

    configure_logging("test_service", uvicorn=True)
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    captured = capsys.readouterr()
    (entry,) = [json.loads(line) for line in captured.out.splitlines()]
    assert entry["message"] == "Application startup complete."
    assert entry["logger"] == "uvicorn.error"
    assert captured.err == ""  # not a second copy in plain text from uvicorn's own handler


def test_with_uvicorn_its_access_line_is_not_logged_because_the_service_logs_each_request(capsys):
    configure_logging("test_service", uvicorn=True)

    logging.getLogger("uvicorn.access").info('127.0.0.1:1 - "GET /pollutants?year=2023" 200')

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_without_uvicorn_the_loggers_of_uvicorn_are_left_alone():
    handler = logging.StreamHandler()
    uvicorn = logging.getLogger("uvicorn")
    uvicorn.addHandler(handler)
    uvicorn.propagate = False

    configure_logging("test_service")

    assert handler in uvicorn.handlers
    assert uvicorn.propagate is False


# What an extra field may carry: text, numbers, lists and dictionaries of those, and a few value
# types that have a safe text form. Anything else is written as its class name, never by content:
# a database URL is a tuple that holds the password, a request holds its headers.


class Credentials(NamedTuple):
    user: str
    password: str


class Holder:
    def __str__(self):
        return "token=SECRETPW"


class Headers(Mapping):
    def __getitem__(self, key):
        return "Bearer SECRETPW"

    def __iter__(self):
        return iter(["authorization"])

    def __len__(self):
        return 1


def line_with(**extra):
    return JsonFormatter().format(logging.makeLogRecord({"msg": "x", "name": "t", **extra}))


@pytest.mark.parametrize(
    "value",
    [Credentials("u", "SECRETPW"), Holder(), Headers(), {"SECRETPW"}, b"SECRETPW", lambda: 1],
)
def test_an_object_is_written_as_its_class_name_never_by_its_content(value):
    line = line_with(thing=value)

    assert "SECRETPW" not in line
    assert json.loads(line)["thing"] == f"<{type(value).__name__}>"


def test_an_object_inside_a_list_or_a_dictionary_is_hidden_too():
    line = line_with(thing={"db": [1, Credentials("u", "SECRETPW")]})

    assert "SECRETPW" not in line
    assert json.loads(line)["thing"] == {"db": [1, "<Credentials>"]}


def test_text_numbers_lists_dictionaries_and_dates_are_written_as_they_are():
    value = {"a": [1, 2.5, True, None, "x"], "when": date(2023, 5, 1), "kg": Decimal("1.50")}

    assert json.loads(line_with(thing=value))["thing"] == {
        "a": [1, 2.5, True, None, "x"],
        "when": "2023-05-01",
        "kg": "1.50",
    }


# A client can make the service log what it chooses (a path of 60,000 letters), so no line is
# allowed to grow without limit: texts are cut, with a mark that says how much was left out.


def test_a_text_of_exactly_the_limit_is_kept_and_one_more_character_is_cut():
    kept = json.loads(line_with(thing="a" * 2000))["thing"]
    cut = json.loads(line_with(thing="a" * 2001))["thing"]

    assert kept == "a" * 2000
    assert cut == "a" * 2000 + "...[truncated 1]"


def test_a_huge_value_gives_a_short_line_that_is_still_valid_json():
    line = line_with(thing="x" * 60_000)

    assert len(line) < 3000
    assert json.loads(line)["thing"].endswith("...[truncated 58000]")


def test_texts_inside_lists_and_dictionaries_are_cut_too():
    thing = json.loads(line_with(thing={"a": ["y" * 2500]}))["thing"]

    assert thing == {"a": ["y" * 2000 + "...[truncated 500]"]}


def test_the_message_is_cut():
    record = logging.makeLogRecord({"msg": "m" * 2100, "name": "t"})

    assert (
        json.loads(JsonFormatter().format(record))["message"] == "m" * 2000 + "...[truncated 100]"
    )


def test_a_traceback_has_a_bigger_limit_than_a_value():
    def record(size):
        try:
            raise ValueError("e" * size)
        except ValueError:
            return logging.makeLogRecord({"msg": "failed", "name": "t", "exc_info": sys.exc_info()})

    short = json.loads(JsonFormatter().format(record(100)))["exception"]
    middle = json.loads(JsonFormatter().format(record(5000)))["exception"]  # over a value's limit
    long = json.loads(JsonFormatter().format(record(20_000)))["exception"]

    assert "truncated" not in short
    assert "truncated" not in middle
    assert len(long) < 8100
    assert "...[truncated " in long
