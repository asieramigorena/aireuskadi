"""JSON logging: one JSON object per line on standard output.

Fields passed with ``extra=`` become keys of the object, e.g. a row left out of a load:

    log.warning(
        "row rejected",
        extra={"source": "eprtr_air", "row_number": 12, "reason": "invalid coordinates"},
    )

The level comes from the environment variable ``LOG_LEVEL`` (INFO by default). The lines are what
Loki and the Grafana dashboards read (``| json | level=... | message=...``), so the keys are the
same in every service: ``time``, ``level``, ``logger``, ``message``, then the extra fields.
"""

import json
import logging
import os
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import PurePath
from uuid import UUID

# Attributes that every LogRecord has: anything else was passed with extra=.
_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


# A client can make the service log what it chooses (a path of 60,000 letters), so no line grows
# without limit: a text is cut and the mark says how much was left out. A traceback may be longer.
MAX_TEXT = 2000
MAX_EXCEPTION = 8000


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated {len(text) - limit}]"


# Types that have a text form that is safe to write. Text, numbers, booleans and None are written
# as they are; lists and dictionaries of those too. Anything else is written as its class name:
# a database URL is a tuple that holds the password, and a request holds its headers.
_AS_TEXT = (Decimal, date, datetime, time, timedelta, UUID, PurePath)


def _safe(value):
    """What may be written for the value of an extra field, never an object by its content."""
    if type(value) is str:
        return _cut(value, MAX_TEXT)
    if value is None or type(value) in (int, float, bool):
        return value
    if isinstance(value, _AS_TEXT):
        return str(value)
    if type(value) in (list, tuple):  # not a NamedTuple, which is a class of its own
        return [_safe(item) for item in value]
    if type(value) is dict:
        return {str(key): _safe(item) for key, item in value.items()}
    return f"<{type(value).__name__}>"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": _cut(record.getMessage(), MAX_TEXT),
        }
        for key, value in record.__dict__.items():
            if key not in _RECORD_FIELDS:
                # An extra field never replaces one of the fields above.
                entry[f"extra_{key}" if key in entry else key] = _safe(value)
        if record.exc_info:
            entry["exception"] = _cut(self.formatException(record.exc_info), MAX_EXCEPTION)
        return json.dumps(entry, ensure_ascii=False)


def _log_uncaught(service: str):
    """A crash as one JSON line, with the traceback inside it, instead of the lines of plain text
    that Python prints, which the log searches cannot read as JSON."""

    def hook(exc_type, exc, traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):  # stopped by hand: nothing failed
            sys.__excepthook__(exc_type, exc, traceback)
            return
        logging.getLogger(service).critical(
            "uncaught exception", exc_info=(exc_type, exc, traceback)
        )

    return hook


def _tidy_uvicorn() -> None:
    """uvicorn installs its own plain-text handlers before it loads the application: remove them
    so its messages go through the JSON handler of the root logger, once. Its access line is
    dropped, because the service logs a record of its own for each request (with no query string)."""
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False


def configure_logging(service: str, *, uvicorn: bool = False) -> None:
    """Send everything the process logs to standard output as JSON.

    `service` names the logger that records an uncaught exception. Pass `uvicorn=True` in a
    service that runs under uvicorn.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    sys.excepthook = _log_uncaught(service)
    if uvicorn:
        _tidy_uvicorn()
