"""JSON logging for the worker: one JSON object per line on standard output.

Fields passed with ``extra=`` become keys of the object, e.g. a row left out of a load:

    log.warning(
        "row rejected",
        extra={"source": "eprtr_air", "row_number": 12, "reason": "invalid coordinates"},
    )

The level comes from the environment variable ``LOG_LEVEL`` (INFO by default).
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime

# Attributes that every LogRecord has: anything else was passed with extra=.
_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RECORD_FIELDS:
                # An extra field never replaces one of the fields above.
                entry[f"extra_{key}" if key in entry else key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
