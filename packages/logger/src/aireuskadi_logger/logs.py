"""JSON logging: one JSON object per line on standard output.

Fields passed with ``extra=`` become keys of the object, e.g. a row left out of a load:

    log.warning(
        "row rejected",
        extra={"source": "eprtr_air", "row_number": 12, "reason": "invalid coordinates"},
    )

The level comes from the environment variable ``LOG_LEVEL`` (INFO by default).

What the formatter does for the caller: an object in an extra field is written as its class name,
texts and lists are cut, the credentials of a URL (``scheme://user:password@host``) are hidden in
every text, and a record that cannot be written gives a fixed line. What it cannot do: a secret
that is not part of a URL. So the caller must never put a token, a key or a password in a message
or in the message of an exception, and must not use a secret as the key of a dictionary. The lines are what
Loki and the Grafana dashboards read (``| json | level=... | message=...``), so the keys are the
same in every service: ``time``, ``level``, ``logger``, ``message``, then the extra fields.
"""

import itertools
import json
import logging
import math
import os
import re
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import PurePath
from uuid import UUID

# Attributes that every LogRecord has: anything else was passed with extra=.
_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


# A client can make the service log what it chooses (a path of 60,000 letters, a list of a million
# items), so no line grows without limit: a text is cut and the mark says how much was left out.
# A traceback may be longer. As a last barrier, a line over MAX_LINE keeps only its core fields.
MAX_TEXT = 2000
MAX_EXCEPTION = 8000
MAX_ITEMS = 100
MAX_DEPTH = 5
MAX_LINE = 16_000


# The credentials of a URL (scheme://user:password@host): a password can get into a log as part of
# a text, in a message, in the message of an exception, in a value. They are hidden wherever they
# are, before the text is cut, so that a cut cannot leave half of a password.
_CREDENTIALS = re.compile(r"(://[^/\s:@]+):[^@\s/]+@")


def _clean(text: str, limit: int) -> str:
    text = _CREDENTIALS.sub(r"\1:***@", text)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated {len(text) - limit}]"


# Types that have a text form that is safe to write.
_AS_TEXT = (Decimal, date, datetime, time, timedelta, UUID, PurePath)


def _key(key) -> str:
    """A key of a dictionary: a text is cut, a number is written, anything else by its class."""
    if type(key) is str:
        return _clean(key, MAX_TEXT)
    if type(key) in (int, bool) and key.bit_length() < 64:
        return str(key)
    return f"<{type(key).__name__}>"


def _safe(value, depth: int = 0):
    """What may be written for the value of an extra field, never an object by its content.

    Text, numbers, booleans and None are written as they are (a text is cut, a number JSON cannot
    print is written as text); lists and dictionaries of those too, up to MAX_ITEMS items and
    MAX_DEPTH levels. A database URL is a tuple that holds the password, and a request holds its
    headers, so anything else is written as its class name.
    """
    if type(value) is str:
        return _clean(value, MAX_TEXT)
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        return value if value.bit_length() < 64 else "<int>"
    if type(value) is float:
        return value if math.isfinite(value) else str(value)  # JSON has no NaN or Infinity
    if isinstance(value, _AS_TEXT):
        return _clean(str(value), MAX_TEXT)
    if type(value) in (list, tuple, dict):
        if depth >= MAX_DEPTH:  # also what stops a list that contains itself
            return f"<{type(value).__name__}>"
        if type(value) is dict:
            safe = {
                _key(k): _safe(v, depth + 1) for k, v in itertools.islice(value.items(), MAX_ITEMS)
            }
            if len(value) > MAX_ITEMS:
                safe["..."] = f"[{len(value) - MAX_ITEMS} more]"
            return safe
        safe = [_safe(item, depth + 1) for item in itertools.islice(value, MAX_ITEMS)]
        if len(value) > MAX_ITEMS:
            safe.append(f"...[{len(value) - MAX_ITEMS} more]")
        return safe
    return f"<{type(value).__name__}>"


def _time(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")


class JsonFormatter(logging.Formatter):
    """One log record as one line of JSON. Texts are cut and objects are written as their class
    name (see `_safe`), so a record can neither grow without limit nor carry a secret. Formatting
    never raises: a record that cannot be written gives a fixed line that does not repeat it."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            line = self._line(record)
        except Exception:  # noqa: BLE001 - a log call must not fail the code that made it
            line = json.dumps(
                {
                    "time": _time(record),
                    "level": "ERROR",
                    "logger": "aireuskadi_logger",
                    "message": "log record could not be formatted",
                    "record_logger": _clean(str(record.name), 200),
                },
                ensure_ascii=False,
            )
        # A lone surrogate cannot be written to the output: it would fail inside the handler.
        return line.encode("utf-8", "replace").decode("utf-8")

    def _line(self, record: logging.LogRecord) -> str:
        entry = {
            "time": _time(record),
            "level": record.levelname,
            "logger": _clean(record.name, MAX_TEXT),
            "message": _clean(record.getMessage(), MAX_TEXT),
        }
        if record.exc_info:
            entry["exception"] = _clean(self.formatException(record.exc_info), MAX_EXCEPTION)
        core = dict(entry)
        for key, value in record.__dict__.items():
            if key not in _RECORD_FIELDS:
                key = _clean(key, MAX_TEXT)
                # An extra field never replaces one of the fields above.
                entry[f"extra_{key}" if key in entry else key] = _safe(value)
        line = json.dumps(entry, ensure_ascii=False)
        if len(line) > MAX_LINE:
            core["fields_dropped"] = len(entry) - len(core)
            line = json.dumps(core, ensure_ascii=False)
        return line


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
    service that runs under uvicorn. Calling it again replaces the handlers, it does not add
    to them.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    logging.raiseExceptions = False  # a failed write must not dump the record on the error output
    sys.excepthook = _log_uncaught(service)
    if uvicorn:
        _tidy_uvicorn()
