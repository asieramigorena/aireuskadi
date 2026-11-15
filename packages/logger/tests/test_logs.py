"""JSON logs: one JSON object per line, with the keys that the Grafana dashboards read."""

import io
import json
import logging
import sys

import pytest
from aireuskadi_logger import JsonFormatter, configure_logging


@pytest.fixture
def lines():
    """A logger that writes through JsonFormatter into a buffer; gives the lines read as JSON."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test_logs")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield lambda: [json.loads(line) for line in buffer.getvalue().splitlines()]
    logger.handlers = []


def test_a_line_has_the_keys_of_the_dashboards_and_the_extra_fields(lines):
    logging.getLogger("test_logs").warning(
        "row rejected", extra={"source": "eprtr_air", "row_number": 12}
    )

    (line,) = lines()
    assert line["level"] == "WARNING"
    assert line["logger"] == "test_logs"
    assert line["message"] == "row rejected"
    assert line["time"].endswith("+00:00")
    assert (line["source"], line["row_number"]) == ("eprtr_air", 12)


def test_an_exception_goes_inside_the_line(lines):
    try:
        raise ValueError("bad row")
    except ValueError:
        logging.getLogger("test_logs").exception("load failed")

    (line,) = lines()
    assert "ValueError: bad row" in line["exception"]


def test_an_object_is_written_by_its_class_never_by_what_it_holds(lines):
    class Secret:
        def __str__(self):
            return "the password"

    logging.getLogger("test_logs").info("x", extra={"engine": Secret()})

    assert lines()[0]["engine"] == "<Secret>"


def test_the_password_of_a_url_is_hidden(lines):
    logging.getLogger("test_logs").error("cannot connect to postgresql://app:hunter2@db:5432/x")

    message = lines()[0]["message"]
    assert "hunter2" not in message
    assert "postgresql://app:***@db:5432/x" in message


def test_a_very_long_text_is_cut(lines):
    logging.getLogger("test_logs").info("a" * 60_000)

    assert len(lines()[0]["message"]) == 2000


def test_a_configured_process_writes_json_on_stdout_at_the_level_of_log_level(capsys, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    configure_logging("test_service")

    logging.getLogger("x").info("not shown")
    logging.getLogger("x").warning("shown")

    (line,) = capsys.readouterr().out.splitlines()
    assert json.loads(line)["message"] == "shown"


def test_a_crash_is_one_json_line(capsys):
    configure_logging("test_service")

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    (line,) = capsys.readouterr().out.splitlines()
    assert json.loads(line)["message"] == "uncaught exception"


def test_with_uvicorn_its_lines_come_out_as_json_once_and_its_access_line_is_dropped(capsys):
    configure_logging("test_service", uvicorn=True)

    logging.getLogger("uvicorn.error").info("started")
    logging.getLogger("uvicorn.access").info("GET /x?secret=1")

    (line,) = capsys.readouterr().out.splitlines()
    assert json.loads(line)["message"] == "started"


def test_a_record_that_cannot_be_written_gives_a_fixed_line_and_never_its_arguments(capsys):
    configure_logging("test_service")

    # Two %s and one argument: the message cannot be formatted.
    logging.getLogger("x").error("connect %s %s", "postgresql://u:SECRET1@h/db")  # noqa: PLE1206

    output = capsys.readouterr()
    assert "SECRET1" not in output.out + output.err
    assert json.loads(output.out)["message"] == "log record could not be written"


def test_a_list_inside_a_list_is_not_followed(lines):
    looped = []
    looped.append(looped)

    logging.getLogger("test_logs").info("x", extra={"values": [1, looped], "ratio": float("nan")})

    line = lines()[0]
    assert line["values"] == [1, "<list>"]
    assert line["ratio"] == "nan"  # JSON has no NaN: Loki could not read the line
