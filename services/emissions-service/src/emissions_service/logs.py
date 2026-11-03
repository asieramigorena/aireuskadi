"""JSON logging: one JSON object per line on standard output, the same format as the worker's.

Fields passed with ``extra=`` become keys of the object. The level comes from the environment
variable ``LOG_LEVEL`` (INFO by default). uvicorn installs its own plain-text handlers before it
loads the application; they are removed so its messages go through the same JSON handler.
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
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # The "request" record of the application replaces uvicorn's access line (which also has the
    # query string), so that one is left without handlers and without propagation.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
