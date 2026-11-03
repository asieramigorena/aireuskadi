"""JSON logging: one JSON object per line on standard output, for every service."""

import io
import json
import logging
import sys
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import PurePosixPath
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


# A log line has to be valid JSON, has to be bounded whatever it is given, and writing it must
# never fail or fall back to something that is not redacted.


def strict(line):
    """Parse like a strict reader (Loki's): NaN and Infinity are not JSON."""

    def refuse(constant):
        raise ValueError(f"{constant} is not valid JSON")

    return json.loads(line, parse_constant=refuse)


def test_nan_and_infinity_are_written_as_text_because_json_does_not_have_them():
    entry = strict(line_with(a=float("nan"), b=float("inf"), c=float("-inf")))

    assert (entry["a"], entry["b"], entry["c"]) == ("nan", "inf", "-inf")


def test_a_key_that_is_not_text_is_written_as_its_class_name_never_by_its_content():
    line = line_with(thing={Credentials("u", "SECRETPW"): 1, (1, 2): 2, 7: 3, "ok": 4})

    assert "SECRETPW" not in line
    assert json.loads(line)["thing"] == {"<Credentials>": 1, "<tuple>": 2, "7": 3, "ok": 4}


def test_a_key_and_the_name_of_a_field_are_cut_like_a_text():
    entry = json.loads(line_with(thing={"k" * 5000: 1}, **{"f" * 5000: 2}))

    assert [len(key) for key in entry["thing"]] == [2000 + len("...[truncated 3000]")]
    assert max(len(key) for key in entry) < 2100


def test_a_long_list_is_cut_to_a_hundred_items_and_says_how_many_were_left_out():
    entry = json.loads(line_with(thing=list(range(1_000_000))))

    assert entry["thing"][:100] == list(range(100))
    assert entry["thing"][100:] == ["...[999900 more]"]


def test_a_big_dictionary_is_cut_to_a_hundred_items_and_says_how_many_were_left_out():
    thing = json.loads(line_with(thing={f"k{i}": i for i in range(200_000)}))["thing"]

    assert len(thing) == 101
    assert thing["..."] == "[199900 more]"


def test_a_list_nested_too_deep_or_pointing_to_itself_is_cut_instead_of_failing():
    deep = current = []
    for _ in range(3000):
        nested = []
        current.append(nested)
        current = nested
    loop = []
    loop.append(loop)

    assert json.loads(line_with(thing=deep))["thing"] == [[[[["<list>"]]]]]
    assert json.loads(line_with(thing=loop))["thing"] == [[[[["<list>"]]]]]


def test_an_integer_too_big_for_json_to_print_is_written_as_its_class_name():
    entry = json.loads(line_with(small=2**63 - 1, edge=2**63, big=10**5000))

    assert (entry["small"], entry["edge"], entry["big"]) == (2**63 - 1, "<int>", "<int>")


def test_the_text_of_a_value_that_is_written_as_text_is_cut_too():
    entry = json.loads(line_with(path=PurePosixPath("/" + "p" * 5000)))

    assert len(entry["path"]) == 2000 + len("...[truncated 3001]")


def test_a_record_that_cannot_be_formatted_gives_a_fixed_valid_line_not_an_error():
    record = logging.makeLogRecord({"msg": "%d things", "args": ("not a number",), "name": "t"})

    entry = json.loads(JsonFormatter().format(record))

    assert (entry["level"], entry["message"]) == ("ERROR", "log record could not be formatted")
    assert entry["record_logger"] == "t"
    assert "not a number" not in json.dumps(entry)  # the arguments are not repeated


def test_a_lone_surrogate_does_not_stop_the_line_from_being_written(capsys):
    configure_logging("test_service")

    logging.getLogger("t").info("x", extra={"v": "ab\ud800cd"})

    captured = capsys.readouterr()
    assert json.loads(captured.out)["v"] == "ab?cd"
    assert captured.err == ""  # logging does not dump the record on the error output


def test_a_whole_line_never_grows_past_its_limit():
    fields = {f"field{i}": "x" * 1900 for i in range(60)}

    line = line_with(**fields)

    assert len(line) <= 16_000
    entry = json.loads(line)
    assert entry["message"] == "x"
    assert entry["fields_dropped"] > 0


class BrokenOutput(io.StringIO):
    def write(self, text):
        raise OSError("the output is closed")


def test_when_the_output_itself_fails_the_record_is_not_dumped_on_the_error_output(
    monkeypatch, capsys
):
    monkeypatch.setattr(sys, "stdout", BrokenOutput())
    configure_logging("test_service")

    logging.getLogger("t").info("a message that carries SECRETPW")

    assert capsys.readouterr().err == ""


# A password can still get into a log as part of a text: in the message, in the message of an
# exception, in a value. The credentials of a URL are hidden wherever they are.

URL = "postgresql+psycopg://reader:SECRETPW@db:5432/air"
HIDDEN = "postgresql+psycopg://reader:***@db:5432/air"


def test_the_password_of_a_url_in_the_message_is_hidden():
    record = logging.makeLogRecord({"msg": "cannot reach %s", "args": (URL,), "name": "t"})

    assert json.loads(JsonFormatter().format(record))["message"] == f"cannot reach {HIDDEN}"


def test_the_password_of_a_url_in_an_exception_is_hidden():
    try:
        raise ValueError(f"bad url {URL}")
    except ValueError:
        record = logging.makeLogRecord({"msg": "failed", "name": "t", "exc_info": sys.exc_info()})

    line = JsonFormatter().format(record)

    assert "SECRETPW" not in line
    assert HIDDEN in json.loads(line)["exception"]


def test_the_password_of_a_url_in_a_value_a_list_or_a_key_is_hidden():
    line = line_with(a=URL, b=[1, {"c": URL}], d={URL: 1})

    assert "SECRETPW" not in line
    entry = json.loads(line)
    assert (entry["a"], entry["b"][1]["c"]) == (HIDDEN, HIDDEN)
    assert list(entry["d"]) == [HIDDEN]


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com/path",
        "https://example.com:8080/a@b",  # a port, then a path with an @
        "mail me at someone@example.com",
        "postgresql://db:5432/air",
        "key: value @ home",
    ],
)
def test_a_text_that_has_no_credentials_in_a_url_is_not_touched(text):
    assert json.loads(line_with(a=text))["a"] == text


def test_two_urls_in_one_text_are_both_hidden():
    entry = json.loads(line_with(a=f"{URL} and {URL}"))

    assert entry["a"] == f"{HIDDEN} and {HIDDEN}"


def test_a_password_that_the_cut_would_split_is_hidden_before_the_cut_not_left_half_visible():
    # The URL starts 35 characters before the limit, so the cut would fall inside the password.
    text = "a" * (2000 - 35) + URL

    line = line_with(a=text)

    assert "SEC" not in line
