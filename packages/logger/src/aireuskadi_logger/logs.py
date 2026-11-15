"""JSON logs: one JSON object per line on standard output, which is what Loki and Grafana read.

Every line has the same keys in every service: time, level, logger, message, and then the fields
given with extra=, for example:

    log.warning("row rejected", extra={"source": "eprtr_air", "row_number": 12})

The level comes from the environment variable LOG_LEVEL (INFO if it is not set).
"""

import json
import logging
import math
import os
import re
import sys
from datetime import UTC, datetime

# The attributes that every log record has. Anything else came with extra=.
STANDARD_FIELDS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

# The password of a URL (postgresql://user:password@host) is hidden wherever it appears.
PASSWORD_IN_URL = re.compile(r"(://[^/\s:@]+):[^@\s/]+@")

# A client can make a service log a very long text (a path of 60,000 letters): it is cut.
MAX_TEXT = 2000


def clean(text: str, limit: int = MAX_TEXT) -> str:
    return PASSWORD_IN_URL.sub(r"\1:***@", text)[:limit]


def simple(value, inside_a_list: bool = False):
    """A text, a number, a boolean or None is written as it is, and a list of them too; anything
    else only by the name of its class, because an object can hold a secret (a database URL, the
    headers of a request). A list inside a list is not followed (it could contain itself)."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # JSON has no NaN or Infinity
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple)) and not inside_a_list:
        return [simple(item, inside_a_list=True) for item in value[:100]]
    return f"<{type(value).__name__}>"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            return self.json_line(record)
        except Exception:  # noqa: BLE001 - a log call must never fail the code that made it
            # A fixed line: the record itself (its arguments) could hold a secret.
            return json.dumps(
                {
                    "level": "ERROR",
                    "logger": record.name,
                    "message": "log record could not be written",
                }
            )

    def json_line(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": clean(record.getMessage()),
        }
        if record.exc_info:
            # A traceback is longer than a text: 8000, as in the Node service.
            line["exception"] = clean(self.formatException(record.exc_info), 8000)
        for key, value in vars(record).items():
            if key not in STANDARD_FIELDS and key not in line:
                line[key] = simple(value)
        # A lone surrogate cannot be written to the output: it is replaced.
        return json.dumps(line, ensure_ascii=False).encode("utf-8", "replace").decode("utf-8")


def configure_logging(service: str, *, uvicorn: bool = False) -> None:
    """Send everything that the process logs to standard output as JSON. Pass `uvicorn=True` in a
    service that runs under uvicorn. Calling it again replaces the handler, it does not add one."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel((os.environ.get("LOG_LEVEL") or "INFO").upper())
    # If writing a line fails, Python would print the record in plain text on the error output.
    logging.raiseExceptions = False

    # A crash is one JSON line too, with its traceback inside.
    def log_crash(kind, error, traceback):
        logging.getLogger(service).critical("uncaught exception", exc_info=(kind, error, traceback))

    sys.excepthook = log_crash

    if uvicorn:
        # uvicorn brings its own handlers of plain text: its lines go through the JSON one instead.
        # Its line per request is dropped: the service writes its own (without the query string).
        for name in ("uvicorn", "uvicorn.error"):
            logging.getLogger(name).handlers = []
            logging.getLogger(name).propagate = True
        logging.getLogger("uvicorn.access").handlers = []
        logging.getLogger("uvicorn.access").propagate = False
