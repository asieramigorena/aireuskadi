import logging
import sys

import pytest


@pytest.fixture(autouse=True)
def keep_logging_state():
    """configure_logging changes the root logger, uvicorn's and sys.excepthook: put them back."""
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access"]
    saved = [(n, logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in names]
    level, hook = logging.getLogger().level, sys.excepthook
    yield
    for name, handlers, propagate in saved:
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate
    logging.getLogger().setLevel(level)
    sys.excepthook = hook
