"""configure_logging: everything the process logs is one JSON object per line on stdout."""

import json
import logging

from emissions_service.logs import configure_logging


def lines(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_a_request_record_is_one_json_line_with_its_fields_as_keys(capsys):
    configure_logging()

    logging.getLogger("emissions_service.access").info(
        "request", extra={"method": "GET", "path": "/pollutants", "status": 200, "duration_ms": 3.2}
    )

    (entry,) = lines(capsys)
    assert entry["message"] == "request"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "emissions_service.access"
    assert (entry["method"], entry["path"], entry["status"], entry["duration_ms"]) == (
        "GET",
        "/pollutants",
        200,
        3.2,
    )


def test_uvicorn_messages_also_come_out_as_json_and_only_once(capsys):
    # uvicorn installs its own plain-text handler before it loads the application.
    uvicorn = logging.getLogger("uvicorn")
    uvicorn.addHandler(logging.StreamHandler())
    uvicorn.propagate = False

    configure_logging()
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    captured = capsys.readouterr()
    (entry,) = [json.loads(line) for line in captured.out.splitlines()]
    assert entry["message"] == "Application startup complete."
    assert entry["logger"] == "uvicorn.error"
    assert captured.err == ""  # not a second copy in plain text from uvicorn's own handler


def test_uvicorns_own_access_line_is_not_logged_because_the_request_record_replaces_it(capsys):
    configure_logging()

    logging.getLogger("uvicorn.access").info('127.0.0.1:1 - "GET /pollutants?year=2023" 200')

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
